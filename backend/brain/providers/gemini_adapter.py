import os
from google import genai
from google.genai import types
from typing import AsyncGenerator
from .base import LLMProvider
from ..gemini.function_calls import get_maya_tools
from ...vision.capture.screen_capture import screen_capture
from ...database.connection import SessionLocal
from ...database.models import UserPreferences
from ...database.crypto import crypto_manager
import logging
import json
import inspect
import re
import httpx
from ...tools.mcp_service import mcp_service
from .fallback import fallback_manager
from ...config.provider_config import (
    ANTHROPIC_KIND,
    GEMINI_KIND,
    OPENAI_COMPATIBLE_KIND,
    base_url_from_env,
    chat_url_for_provider,
    detect_provider_from_key,
    fallback_models_for_provider,
    model_from_env,
    model_for_provider,
    normalize_provider,
    provider_from_env,
    provider_spec,
)

logger = logging.getLogger(__name__)


class ThinkStripper:
    """Streaming-safe filter that removes model chain-of-thought that some
    OpenAI-compatible providers embed inside the `content` field instead of a
    separate `reasoning_content` field.

    Handles two leak styles across chunk boundaries:
      1. Explicit tags: <think>...</think> (also <thinking>, <reasoning>).
      2. A leading reasoning preamble with no tags, terminated by a marker
         line such as "Final answer:" / "Response:" — only stripped when the
         very first visible characters look like meta-reasoning.

    Only style (1) is applied unconditionally (safe: tags are unambiguous).
    Style (2) is conservative and off by default to avoid eating real text.
    """

    _OPEN_TAGS = ("<think>", "<thinking>", "<reasoning>")
    _CLOSE_TAGS = ("</think>", "</thinking>", "</reasoning>")
    # Longest token we might need to hold back while waiting for more chars.
    _MAX_PARTIAL = len("<thinking>")

    def __init__(self):
        self._in_think = False
        self._pending = ""  # chars held back because they might start a tag

    def feed(self, text: str) -> str:
        if not text:
            return ""
        buf = self._pending + text
        self._pending = ""
        out = []
        i = 0
        n = len(buf)
        while i < n:
            if self._in_think:
                close_pos, tag = self._find_first(buf, self._CLOSE_TAGS, i)
                if close_pos == -1:
                    # No closing tag yet; keep a small tail in case it's split.
                    self._pending = buf[max(i, n - self._MAX_PARTIAL):]
                    return "".join(out)
                i = close_pos + len(tag)
                self._in_think = False
            else:
                open_pos, tag = self._find_first(buf, self._OPEN_TAGS, i)
                if open_pos == -1:
                    # Emit everything except a possible partial tag at the tail.
                    safe_end = self._safe_emit_end(buf, i, n)
                    out.append(buf[i:safe_end])
                    self._pending = buf[safe_end:]
                    return "".join(out)
                out.append(buf[i:open_pos])
                i = open_pos + len(tag)
                self._in_think = True
        return "".join(out)

    def flush(self) -> str:
        """Emit anything held back once the stream ends."""
        tail = "" if self._in_think else self._pending
        self._pending = ""
        return tail

    # Unambiguous plain-text reasoning-leak signatures. No legitimate final
    # answer contains these as a preamble, so acting on them is safe. Gemini
    # Flash leaks its planning as plain text ("Let's formulate the final
    # response.", "Final Answer:", "If you are done, output...") before the real
    # (usually Bengali) answer — these cover the observed patterns.
    _LEAK_MARKERS = (
        "👤 my thought process", "my thought process:",
        "here's my thought process", "here is my thought process",
        "let's formulate", "let us formulate",
        "final answer:", "final response:",
        "if you are done", "output the final answer",
        "output must be", "no reasoning, planning",
        "language: bengali", "language: banglish", "language: hindi",
        "clean and professional", "matching the user's input",
        # Observed live: Gemini echoing the anti-hallucination directive itself
        # ("Do not explain your steps... Keep it concise and professional.")
        # instead of silently following it — glued directly onto the real
        # (Bengali/Banglish) answer with no separator.
        "do not explain your steps", "just provide the final answer",
        "provide the final answer in the user", "do not use any companion terms",
        "keep it concise and professional", "if the execution is complete",
        "provide your final response to the user",
    )

    @classmethod
    def clean_full(cls, text: str) -> str:
        """Best-effort cleanup for a COMPLETE assistant message (non-streaming
        paths / TTS / Telegram). Removes <think> blocks, then — only if an
        unambiguous reasoning-leak marker is present — keeps just the model's
        real answer (its final non-Latin block) and drops the English planning.

        Fail-safe: if no leak marker is found, or no non-Latin answer block can
        be located, the text is returned unchanged (never eats real content).
        """
        if not text:
            return text

        import re
        # 1) Strip explicit <think>/<thinking>/<reasoning> blocks anywhere.
        cleaned = re.sub(r"(?is)<(think|thinking|reasoning)>.*?</\1>", "", text).strip()

        # 2) Plain-text leak: only act if an unambiguous planning marker appears.
        low = cleaned.lower()
        if not any(m in low for m in cls._LEAK_MARKERS):
            return cleaned

        # The model reasons in English (Latin) and answers in the user's own
        # language, appending the real answer AFTER the planning. Take the LAST
        # maximal non-Latin (Bengali/Hindi/CJK) block — that is the answer, even
        # when the reasoning quoted a draft of it earlier.
        non_latin_spans = [s for s in re.findall(r"[^A-Za-z]+", cleaned)
                           if re.search(r"[ऀ-ॿঀ-৿぀-ヿ一-鿿]", s)]
        if non_latin_spans:
            candidate = non_latin_spans[-1].strip(" \t\n\r\"'`.:;,-()")
            if len(candidate) >= 3:
                return candidate

        # Answer is also English → can't split reliably. Fail safe.
        return cleaned

    @staticmethod
    def _find_first(buf, tags, start):
        best, best_tag = -1, ""
        for t in tags:
            p = buf.find(t, start)
            if p != -1 and (best == -1 or p < best):
                best, best_tag = p, t
        return best, best_tag

    def _safe_emit_end(self, buf, start, n):
        """Return an index up to which it's safe to emit, holding back a tail
        that could be the beginning of a split open-tag like '<thi'."""
        tail_start = max(start, n - self._MAX_PARTIAL)
        for cut in range(tail_start, n):
            frag = buf[cut:]
            if any(t.startswith(frag) for t in self._OPEN_TAGS):
                return cut
        return n


def _model_for_provider(provider: str, stored_model: str | None) -> str:
    from ...config.model_config import get_model

    return model_for_provider(provider, stored_model, get_model)


def clean_context(context: list[dict]) -> list[dict]:
    """
    Cleans the context list to satisfy strict LLM APIs (especially Google Gemini).
    1. Ensures every 'tool_call' role is immediately followed by a 'function' response.
       If missing, inserts a simulated function response.
    2. Removes any stray 'function' responses that don't have a preceding 'tool_call'.
    3. Merges consecutive messages of the same role (user with user, assistant with assistant) 
       to prevent alternating role violations.
    """
    system_msgs = [m for m in context if m.get("role") == "system"]
    raw_msgs = [m for m in context if m.get("role") != "system"]
    
    # 1. Ensure tool_call is followed by function
    temp_msgs = []
    i = 0
    while i < len(raw_msgs):
        msg = raw_msgs[i]
        role = msg.get("role")
        
        if role == "tool_call":
            temp_msgs.append(msg)
            if i + 1 < len(raw_msgs) and raw_msgs[i+1].get("role") == "function":
                temp_msgs.append(raw_msgs[i+1])
                i += 2
            else:
                temp_msgs.append({
                    "role": "function",
                    "name": msg.get("name", "tool"),
                    "content": "Error: Tool execution was interrupted or failed to return a response."
                })
                i += 1
        elif role == "function":
            # Stray function response, skip it
            i += 1
        else:
            temp_msgs.append(msg)
            i += 1
            
    # 2. Merge consecutive messages of the same role
    merged_msgs = []
    for msg in temp_msgs:
        if not merged_msgs:
            merged_msgs.append(dict(msg))
            continue
            
        last = merged_msgs[-1]
        if msg["role"] == "user" and last["role"] == "user":
            last["content"] = f"{last['content']}\n{msg['content']}"
        elif msg["role"] == "assistant" and last["role"] == "assistant":
            last["content"] = f"{last['content']}\n{msg['content']}"
        else:
            merged_msgs.append(dict(msg))
            
    return system_msgs + merged_msgs

def convert_context_to_openai_messages(context: list[dict]) -> list[dict]:
    # Clean the context first to ensure consistency across all providers
    context = clean_context(context)
    messages = []
    last_tool_call_id = None
    for msg in context:
        role = msg["role"]
        if role == "system":
            messages.append({"role": "system", "content": msg["content"]})
        elif role == "user":
            messages.append({"role": "user", "content": msg["content"]})
        elif role == "assistant":
            openai_msg = {"role": "assistant", "content": msg["content"]}
            if "reasoning_content" in msg and msg["reasoning_content"]:
                openai_msg["reasoning_content"] = msg["reasoning_content"]
            messages.append(openai_msg)
        elif role == "tool_call":
            last_tool_call_id = f"call_{len(messages)}"
            openai_msg = {
                "role": "assistant",
                "content": msg.get("content"),
                "tool_calls": [
                    {
                        "id": last_tool_call_id,
                        "type": "function",
                        "function": {
                            "name": msg["name"],
                            "arguments": json.dumps(msg["args"])
                        }
                    }
                ]
            }
            if "reasoning_content" in msg and msg["reasoning_content"]:
                openai_msg["reasoning_content"] = msg["reasoning_content"]
            messages.append(openai_msg)
        elif role == "function":
            t_id = last_tool_call_id if last_tool_call_id else f"call_{len(messages)}"
            messages.append({
                "role": "tool",
                "tool_call_id": t_id,
                "name": msg["name"],
                "content": msg["content"]
            })
            last_tool_call_id = None
    return messages

def _parse_param_descs(doc: str) -> dict:
    """Extract param-name → description from Google-style Args block."""
    descs = {}
    in_args = False
    for line in (doc or "").split("\n"):
        s = line.strip()
        if s.lower().startswith("args:"):
            in_args = True
            continue
        if in_args:
            if not s or s.lower().startswith("returns:"):
                in_args = False
                continue
            m = re.match(r"(\w+)\s*(?:\(.*?\))?:\s*(.*)", s)
            if m:
                descs[m.group(1)] = m.group(2).strip()
    return descs


_ACTION_ENUMS = {
    "manage_window": ["maximize", "minimize", "restore", "close", "snap_left", "snap_right"],
    "control_display": ["pc_only", "duplicate", "extend", "second_only"],
    "control_brightness": ["up", "down"],
    "perform_shortcut": [
        "screenshot", "lock", "snap_left", "snap_right", "show_desktop",
        "open_settings", "open_task_manager", "open_file_explorer",
        "copy", "paste", "undo", "find", "save",
        "play_pause", "mute", "new_tab", "close_tab", "refresh",
        "zoom_in", "zoom_out", "sleep", "shutdown", "restart", "hibernate",
    ],
    "wifi_toggle": ["on", "off"],
    "bluetooth_toggle": ["on", "off"],
    "file": [
        "copy", "move", "rename", "delete", "mkdir", "read", "write",
        "ls", "search", "delete_by_name", "organize",
    ],
    "pc": [
        "volume", "brightness", "lock", "mute", "screenshot", "sleep",
        "shutdown", "restart", "hibernate",
        "clipboard_read", "clipboard_write",
        "process_list", "process_kill",
        "battery", "network", "stats", "active_windows",
        "wifi_scan", "wifi_connect", "wifi_disconnect", "wifi_status", "wifi_toggle",
        "bt_status", "bt_toggle", "bt_list", "bt_remove",
    ],
}


def convert_tools_to_openai_tools(tools: list) -> list:
    openai_tools = []
    for func in tools:
        if isinstance(func, dict):
            if func.get("type") == "function" and func.get("function", {}).get("name"):
                openai_tools.append(func)
            elif func.get("name"):
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": func["name"],
                        "description": func.get("description") or f"Call function {func['name']}",
                        "parameters": func.get("parameters") or func.get("input_schema") or {
                            "type": "object",
                            "properties": {},
                        },
                    },
                })
            continue

        if not hasattr(func, "__name__"):
            continue
        name = func.__name__
        doc = func.__doc__ or ""
        desc = doc.strip().split("\n")[0] if doc else f"Call function {name}"
        param_descs = _parse_param_descs(doc)
        
        sig = inspect.signature(func)
        properties = {}
        required = []
        for param_name, param in sig.parameters.items():
            if param_name in ("self", "args", "kwargs"):
                continue
            param_type = "string"
            if param.annotation == int:
                param_type = "integer"
            elif param.annotation == float:
                param_type = "number"
            elif param.annotation == bool:
                param_type = "boolean"
            elif param.annotation == list:
                param_type = "array"
            elif param.annotation == dict:
                param_type = "object"
            pdesc = param_descs.get(param_name, f"Parameter {param_name}")
            prop = {"type": param_type, "description": pdesc}
            # Add enum constraint for action parameters
            if param_name == "action" and name in _ACTION_ENUMS:
                prop["enum"] = _ACTION_ENUMS[name]
            properties[param_name] = prop
            if param.default == inspect.Parameter.empty:
                required.append(param_name)
        openai_tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": desc,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        })
    return openai_tools


def convert_tools_to_gemini_tools(tools: list) -> list:
    """Convert provider-neutral function dictionaries for the Gemini SDK.

    Native Python callables and existing ``types.Tool`` objects pass through
    unchanged. MCP discovery returns simple dictionaries so the same schema can
    also be used by OpenAI-compatible and Anthropic providers.
    """
    gemini_tools = []
    for tool in tools:
        if not isinstance(tool, dict):
            gemini_tools.append(tool)
            continue

        declaration = (
            tool.get("function") or {}
            if tool.get("type") == "function"
            else tool
        )
        name = declaration.get("name")
        if not name:
            logger.warning("Skipping tool schema without a function name.")
            continue

        gemini_tools.append(
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name=name,
                        description=(
                            declaration.get("description")
                            or f"Call function {name}"
                        ),
                        parameters=(
                            declaration.get("parameters")
                            or declaration.get("input_schema")
                            or {"type": "object", "properties": {}}
                        ),
                    )
                ]
            )
        )
    return gemini_tools


def convert_tools_to_anthropic_tools(tools: list) -> list:
    anthropic_tools = []
    for tool in convert_tools_to_openai_tools(tools):
        fn = tool.get("function", {})
        if not fn.get("name"):
            continue
        anthropic_tools.append({
            "name": fn["name"],
            "description": fn.get("description") or f"Call function {fn['name']}",
            "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
        })
    return anthropic_tools


def _as_anthropic_blocks(content) -> list:
    if isinstance(content, list):
        return content
    return [{"type": "text", "text": "" if content is None else str(content)}]


def _append_anthropic_message(messages: list[dict], role: str, content) -> None:
    if messages and messages[-1]["role"] == role:
        messages[-1]["content"] = _as_anthropic_blocks(messages[-1]["content"]) + _as_anthropic_blocks(content)
        return
    messages.append({"role": role, "content": content})


def _coerce_tool_input(args) -> dict:
    if isinstance(args, dict):
        return args
    if isinstance(args, str):
        try:
            parsed = json.loads(args) if args else {}
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def convert_context_to_anthropic_messages(context: list[dict]) -> tuple[str | None, list[dict]]:
    context = clean_context(context)
    system_parts = []
    messages = []
    last_tool_use_id = None

    for msg in context:
        role = msg["role"]
        if role == "system":
            if msg.get("content"):
                system_parts.append(msg["content"])
        elif role == "user":
            _append_anthropic_message(messages, "user", msg.get("content", ""))
        elif role == "assistant":
            if msg.get("content"):
                _append_anthropic_message(messages, "assistant", msg.get("content", ""))
            for tool_call in msg.get("tool_calls") or []:
                fn = tool_call.get("function") or {}
                tool_use_id = tool_call.get("id") or f"toolu_{len(messages)}"
                args = _coerce_tool_input(fn.get("arguments") or {})
                last_tool_use_id = tool_use_id
                _append_anthropic_message(messages, "assistant", [{
                    "type": "tool_use",
                    "id": tool_use_id,
                    "name": fn.get("name") or "tool",
                    "input": args,
                }])
        elif role == "tool_call":
            tool_use_id = f"toolu_{len(messages)}"
            last_tool_use_id = tool_use_id
            _append_anthropic_message(messages, "assistant", [{
                "type": "tool_use",
                "id": tool_use_id,
                "name": msg.get("name", "tool"),
                "input": _coerce_tool_input(msg.get("args", {})),
            }])
        elif role in ("function", "tool"):
            tool_use_id = msg.get("tool_call_id") or last_tool_use_id or f"toolu_{len(messages)}"
            _append_anthropic_message(messages, "user", [{
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": msg.get("content", ""),
            }])
            last_tool_use_id = None

    return ("\n\n".join(system_parts) if system_parts else None), messages


class GeminiAdapter(LLMProvider):
    def __init__(self):
        self.client = None
        self.reload_key()
        
    def reload_key(self):
        """Loads key from DB (encrypted), falls back to .env, and configures genai/custom provider."""
        fallback_manager.clear_all()
        db = SessionLocal()
        try:
            env_api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
            env_provider = provider_from_env()
            env_model = model_from_env()
            env_base_url = base_url_from_env()

            pref = db.query(UserPreferences).filter(UserPreferences.key == "GEMINI_API_KEY").first()
            api_key = None
            if env_provider and env_api_key:
                api_key = env_api_key
                logger.info("Loaded AI API Key from environment provider override.")
            elif pref and pref.value:
                api_key = (crypto_manager.decrypt(pref.value) or "").strip()
                if api_key:
                    logger.info("Loaded Gemini API Key from encrypted database.")
                else:
                    logger.warning("Encrypted Gemini API Key could not be decrypted. Falling back to environment.")

            if not api_key:
                api_key = env_api_key
                if api_key:
                    logger.info("Loaded Gemini API Key from environment.")

            if not api_key:
                logger.warning("No Gemini API Key found. Maya will not be able to respond.")
                self.api_key = None
                self.client = None
                return
            
            # Load stored provider if any
            provider_pref = db.query(UserPreferences).filter(UserPreferences.key == "GEMINI_API_PROVIDER").first()
            stored_provider = None
            if provider_pref and provider_pref.value:
                try:
                    stored_provider = normalize_provider(crypto_manager.decrypt(provider_pref.value))
                except:
                    pass

            base_url_pref = db.query(UserPreferences).filter(UserPreferences.key == "GEMINI_API_BASE_URL").first()
            stored_base_url = None
            if base_url_pref and base_url_pref.value:
                try:
                    stored_base_url = (crypto_manager.decrypt(base_url_pref.value) or "").strip()
                except:
                    pass
            
            # Load stored active model if any
            model_pref = db.query(UserPreferences).filter(UserPreferences.key == "GEMINI_ACTIVE_MODEL").first()
            stored_model = None
            if model_pref and model_pref.value:
                try:
                    stored_model = crypto_manager.decrypt(model_pref.value)
                except:
                    pass

            self.api_key = api_key
            self.client = None
            self.api_base_url = env_base_url or stored_base_url
            self.provider_error = None
            effective_stored_model = env_model or (None if env_provider else stored_model)
            # Whether the user has explicitly pinned a concrete model in Settings
            # (vs. leaving it "auto"). Only when NOT pinned should a per-message
            # model_tier be allowed to pick the model for a given call.
            self.model_is_pinned = bool((effective_stored_model or "").strip())

            # Determine provider
            if env_provider:
                self.api_provider = detect_provider_from_key(api_key, env_provider)
            elif stored_provider:
                self.api_provider = stored_provider
            else:
                self.api_provider = detect_provider_from_key(api_key)
            
            # Set URL and Model based on selected provider
            spec = provider_spec(self.api_provider)
            if spec.kind == GEMINI_KIND:
                self.api_provider = "gemini"
                self.api_url = None
                self.model_name = _model_for_provider(self.api_provider, effective_stored_model)
                self.client = genai.Client(api_key=api_key)
                logger.info("Universal Adapter: Configured for native Google Gemini API.")
            elif spec.kind == ANTHROPIC_KIND:
                self.api_url = spec.api_url
                self.model_name = _model_for_provider(self.api_provider, effective_stored_model)
                logger.info("Universal Adapter: Configured for Claude API.")
            elif spec.kind == OPENAI_COMPATIBLE_KIND:
                self.api_url = chat_url_for_provider(self.api_provider, self.api_base_url)
                self.model_name = _model_for_provider(self.api_provider, effective_stored_model)
                if not self.api_url:
                    self.provider_error = (
                        f"{spec.label} requires a base URL in Settings "
                        "(for Cloudflare use https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/ai)."
                    )
                    logger.error("Universal Adapter: %s", self.provider_error)
                else:
                    logger.info("Universal Adapter: Configured for %s.", spec.label)
            else:
                self.api_provider = "gemini"
                self.api_url = None
                self.model_name = _model_for_provider(self.api_provider, effective_stored_model)
                self.client = genai.Client(api_key=api_key)
                logger.info("Universal Adapter: Configured for native Google Gemini API.")
        finally:
            db.close()

    def _resolve_primary_model(self, model_tier: str = None) -> str:
        """
        Picks the model to try first for this call. A per-message tier
        (from AnalysisPass / BudgetManager) only takes effect when the user
        hasn't pinned a concrete model in Settings and we're on the native
        Gemini provider (tiers are only defined for Gemini in models.yaml).
        Otherwise falls back to the adapter's configured self.model_name.
        """
        if self.api_provider == "gemini" and not self.model_is_pinned and model_tier in ("fast", "reasoning", "thinking"):
            return _model_for_provider("gemini", model_tier)
        return self.model_name

    async def probe_model(self, model_name: str) -> bool:
        """Lightweight health probe of a model to check if it has recovered from cooldown."""
        if not hasattr(self, "api_key") or not self.api_key:
            return False

        if getattr(self, "provider_error", None) or (self.api_provider != "gemini" and not getattr(self, "api_url", None)):
            return False

        if provider_spec(self.api_provider).kind == ANTHROPIC_KIND:
            try:
                headers = {
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": model_name,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 5,
                }
                async with httpx.AsyncClient() as client:
                    response = await client.post(self.api_url, headers=headers, json=payload, timeout=10.0)
                    return response.status_code == 200
            except Exception as e:
                logger.debug(f"[Fallback] Probe failed for Claude model {model_name}: {e}")
                return False

        if self.api_provider != "gemini":
            try:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": model_name,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 5
                }
                async with httpx.AsyncClient() as client:
                    response = await client.post(self.api_url, headers=headers, json=payload, timeout=10.0)
                    return response.status_code == 200
            except Exception as e:
                logger.debug(f"[Fallback] Probe failed for custom provider model {model_name}: {e}")
                return False
        else:
            if not self.client:
                return False
            try:
                # Use generate_content with a simple string "ping" and max_output_tokens=5
                await self.client.aio.models.generate_content(
                    model=model_name,
                    contents="ping",
                    config=types.GenerateContentConfig(max_output_tokens=5)
                )
                return True
            except Exception as e:
                logger.debug(f"[Fallback] Probe failed for native Gemini model {model_name}: {e}")
                return False

    async def generate_custom_response(self, context: list[dict], tools: list) -> str:
        if getattr(self, "provider_error", None):
            return self.provider_error
        if not getattr(self, "api_url", None):
            return "The selected AI provider is missing its API URL. Please update Settings."
        if provider_spec(self.api_provider).kind == ANTHROPIC_KIND:
            return await self.generate_anthropic_response(context, tools)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        if self.api_provider == "openrouter":
            headers["HTTP-Referer"] = "http://localhost:1420"
            headers["X-Title"] = "Maya AI"
            
        messages = convert_context_to_openai_messages(context)
        openai_tools = convert_tools_to_openai_tools(tools)
        
        models_to_try = [self.model_name]
        for m in fallback_models_for_provider(self.api_provider):
            if m not in models_to_try:
                models_to_try.append(m)
                        
        last_error = None
        available_models = fallback_manager.get_available_models(models_to_try)
        
        for model in available_models:
            payload = {
                "model": model,
                "messages": messages,
                "temperature": 0.7
            }
            if openai_tools:
                payload["tools"] = openai_tools
                
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(self.api_url, headers=headers, json=payload, timeout=30.0)
                    response.raise_for_status()
                    if model != self.model_name:
                        logger.info(f"Using fallback model {model} for this request due to success.")
                    fallback_manager.mark_success(model)
                    data = response.json()
                    choice = data["choices"][0]
                    message = choice.get("message", {})
                    
                    if "tool_calls" in message and message["tool_calls"]:
                        fc = message["tool_calls"][0]["function"]
                        try:
                            args = json.loads(fc["arguments"]) if fc.get("arguments") else {}
                        except:
                            args = {}
                        return f"TOOL_CALL:{fc['name']}:{args}"
                        
                    return ThinkStripper.clean_full(message.get("content", "")) or "Done."
            except (httpx.NetworkError, httpx.ConnectError, httpx.ConnectTimeout) as net_err:
                logger.warning(f"Global network connection error with model {model}: {net_err}")
                last_error = net_err
                # Do not call mark_failed for network connection drops
            except Exception as e:
                err_detail = f"{e} | Response: {getattr(e.response, 'text', '')}" if hasattr(e, "response") and getattr(e.response, "text", None) else str(e)
                logger.warning(f"Custom LLM API failed with model {model}: {err_detail}")
                fallback_manager.mark_failed(model, err_detail)
                last_error = e
                
        if last_error:
            logger.error(f"Custom LLM API Error after trying all models: {last_error}")
        from ...system.state_manager import state_manager
        if state_manager.state.active_mode in ("friendly", "companion"):
            return "দুঃখিত, আমার একটু সমস্যা হচ্ছে।"
        return "I'm sorry, I encountered an error while processing that."

    async def generate_custom_stream(self, context: list[dict], tools: list) -> AsyncGenerator[str, None]:
        if getattr(self, "provider_error", None):
            yield self.provider_error
            return
        if not getattr(self, "api_url", None):
            yield "The selected AI provider is missing its API URL. Please update Settings."
            return
        if provider_spec(self.api_provider).kind == ANTHROPIC_KIND:
            async for chunk in self.generate_anthropic_stream(context, tools):
                yield chunk
            return

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        if self.api_provider == "openrouter":
            headers["HTTP-Referer"] = "http://localhost:1420"
            headers["X-Title"] = "Maya AI"
            
        messages = convert_context_to_openai_messages(context)
        openai_tools = convert_tools_to_openai_tools(tools)
        
        models_to_try = [self.model_name]
        for m in fallback_models_for_provider(self.api_provider):
            if m not in models_to_try:
                models_to_try.append(m)
                        
        stream_started = False
        last_error = None
        available_models = fallback_manager.get_available_models(models_to_try)
        
        for model in available_models:
            payload = {
                "model": model,
                "messages": messages,
                "temperature": 0.7,
                "stream": True
            }
            if openai_tools:
                payload["tools"] = openai_tools
                
            try:
                tool_calls_buffer = {}
                reasoning_content_buffer = ""
                think_stripper = ThinkStripper()
                async with httpx.AsyncClient() as client:
                    async with client.stream("POST", self.api_url, headers=headers, json=payload, timeout=30.0) as response:
                        response.raise_for_status()
                        if model != self.model_name:
                            logger.info(f"Using fallback model {model} for this stream due to success.")
                        fallback_manager.mark_success(model)
                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                data_str = line[6:].strip()
                                if data_str == "[DONE]":
                                    break
                                try:
                                    data_json = json.loads(data_str)
                                    choices = data_json.get("choices", [])
                                    if not choices:
                                        continue
                                    choice = choices[0]
                                    delta = choice.get("delta", {})
                                    
                                    if "reasoning_content" in delta and delta["reasoning_content"]:
                                        reasoning_content_buffer += delta["reasoning_content"]
                                        yield {
                                            "type": "reasoning",
                                            "content": delta["reasoning_content"]
                                        }
                                    
                                    if "content" in delta and delta["content"]:
                                        stream_started = True
                                        visible = think_stripper.feed(delta["content"])
                                        if visible:
                                            yield visible

                                    if "tool_calls" in delta and delta["tool_calls"]:
                                        stream_started = True
                                        for tc in delta["tool_calls"]:
                                            idx = tc.get("index", 0)
                                            if idx not in tool_calls_buffer:
                                                tool_calls_buffer[idx] = {"name": "", "arguments": ""}
                                            
                                            if "function" in tc:
                                                func = tc["function"]
                                                if "name" in func and func["name"]:
                                                    tool_calls_buffer[idx]["name"] = func["name"]
                                                if "arguments" in func and func["arguments"]:
                                                    tool_calls_buffer[idx]["arguments"] += func["arguments"]
                                except Exception as e:
                                    logger.error(f"Error parsing SSE chunk: {e}")

                # Emit any text held back by the think-stripper at stream end.
                tail = think_stripper.flush()
                if tail:
                    yield tail

                # Yield all buffered tool calls
                for idx, tc in tool_calls_buffer.items():
                    if tc["name"]:
                        try:
                            args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                        except:
                            args = {}
                        yield {
                            "type": "tool_call",
                            "name": tc["name"],
                            "args": args,
                            "reasoning_content": reasoning_content_buffer
                        }
                # Successfully finished streaming from this model
                break
            except Exception as e:
                logger.warning(f"Custom LLM Stream failed with model {model} (started={stream_started}): {e}")
                if not stream_started:
                    fallback_manager.mark_failed(model, str(e))
                last_error = e
                if stream_started:
                    break
        else:
            if not stream_started and last_error:
                if isinstance(last_error, httpx.HTTPStatusError):
                    try:
                        body = await last_error.response.aread()
                        logger.error(f"Custom LLM Stream HTTP Error Response: {body.decode('utf-8')}")
                    except Exception as read_err:
                        logger.error(f"Could not read HTTP error response: {read_err}")
                logger.error(f"Custom LLM Stream Error: {last_error}")
                from ...system.state_manager import state_manager
                if state_manager.state.active_mode in ("friendly", "companion"):
                    yield " দুঃখিত, আমার একটু সমস্যা হচ্ছে।"
                else:
                    yield " I'm sorry, I encountered an error while thinking."
        
    async def generate_anthropic_response(self, context: list[dict], tools: list) -> str:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        system_instruction, messages = convert_context_to_anthropic_messages(context)
        anthropic_tools = convert_tools_to_anthropic_tools(tools)
        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": 2048,
            "temperature": 0.7,
        }
        if system_instruction:
            payload["system"] = system_instruction
        if anthropic_tools:
            payload["tools"] = anthropic_tools

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.api_url, headers=headers, json=payload, timeout=30.0)
                response.raise_for_status()
            fallback_manager.mark_success(self.model_name)
            data = response.json()
            text_parts = []
            for block in data.get("content", []):
                block_type = block.get("type")
                if block_type == "text":
                    text_parts.append(block.get("text", ""))
                elif block_type == "tool_use":
                    return f"TOOL_CALL:{block.get('name', 'tool')}:{block.get('input') or {}}"
            return ThinkStripper.clean_full("".join(text_parts)) or "Done."
        except Exception as e:
            fallback_manager.mark_failed(self.model_name, str(e))
            logger.error(f"Claude API Error: {e}")
            return "I'm sorry, I encountered an error while processing that."

    async def generate_anthropic_stream(self, context: list[dict], tools: list) -> AsyncGenerator[str, None]:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        system_instruction, messages = convert_context_to_anthropic_messages(context)
        anthropic_tools = convert_tools_to_anthropic_tools(tools)
        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": 2048,
            "temperature": 0.7,
            "stream": True,
        }
        if system_instruction:
            payload["system"] = system_instruction
        if anthropic_tools:
            payload["tools"] = anthropic_tools

        tool_blocks: dict[int, dict] = {}
        current_index = None
        stream_started = False
        think_stripper = ThinkStripper()

        try:
            async with httpx.AsyncClient() as client:
                async with client.stream("POST", self.api_url, headers=headers, json=payload, timeout=30.0) as response:
                    response.raise_for_status()
                    fallback_manager.mark_success(self.model_name)
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:].strip()
                        if not data_str or data_str == "[DONE]":
                            continue
                        try:
                            event = json.loads(data_str)
                        except Exception as parse_err:
                            logger.error(f"Error parsing Claude SSE chunk: {parse_err}")
                            continue

                        event_type = event.get("type")
                        if event_type == "content_block_start":
                            current_index = event.get("index")
                            block = event.get("content_block") or {}
                            if block.get("type") == "tool_use":
                                tool_blocks[current_index] = {
                                    "name": block.get("name", ""),
                                    "arguments": "",
                                }
                        elif event_type == "content_block_delta":
                            delta = event.get("delta") or {}
                            delta_type = delta.get("type")
                            if delta_type == "text_delta" and delta.get("text"):
                                stream_started = True
                                visible = think_stripper.feed(delta["text"])
                                if visible:
                                    yield visible
                            elif delta_type == "input_json_delta" and current_index in tool_blocks:
                                tool_blocks[current_index]["arguments"] += delta.get("partial_json", "")
                        elif event_type == "content_block_stop":
                            current_index = None

            tail = think_stripper.flush()
            if tail:
                yield tail

            for block in tool_blocks.values():
                if not block.get("name"):
                    continue
                try:
                    args = json.loads(block.get("arguments") or "{}")
                except Exception:
                    args = {}
                yield {
                    "type": "tool_call",
                    "name": block["name"],
                    "args": args,
                }
        except Exception as e:
            logger.error(f"Claude API Stream Error: {e}")
            if not stream_started:
                fallback_manager.mark_failed(self.model_name, str(e))
            yield " I'm sorry, I encountered an error while thinking."

    async def generate_response(self, context: list[dict], prompt: str, image_base64: str = None, override_tools: list = None, model_tier: str = None) -> str:
        if not hasattr(self, "api_key") or not self.api_key:
            return "I am missing my API key. Please configure it in Settings."
            
        if self.api_provider != "gemini":
            tools_to_use = override_tools if override_tools is not None else get_maya_tools()
            return await self.generate_custom_response(context, tools_to_use)
            
        context = clean_context(context)
        try:
            # Build history and extract system instruction
            contents = []
            system_instruction = None
            for msg in context:
                if msg["role"] == "system":
                    system_instruction = (
                        f"{system_instruction}\n\n{msg['content']}"
                        if system_instruction
                        else msg["content"]
                    )
                    continue
                
                if msg["role"] == "function":
                    part = types.Part.from_function_response(name=msg.get("name", "tool"), response={"result": msg["content"]})
                    target_role = "user"
                elif msg["role"] == "tool_call":
                    fc = types.FunctionCall(name=msg.get("name", "tool"), args=msg.get("args", {}))
                    part = types.Part(function_call=fc, thought_signature=msg.get("thought_signature"))
                    target_role = "model"
                else:
                    part = types.Part.from_text(text=msg["content"])
                    target_role = "user" if msg["role"] == "user" else "model"
                
                if contents and contents[-1].role == target_role:
                    contents[-1].parts.append(part)
                else:
                    contents.append(types.Content(role=target_role, parts=[part]))
            
            # If vision context is provided, attach it to the final user message
            if image_base64 and len(contents) > 0 and contents[-1].role == "user":
                import base64
                image_bytes = base64.b64decode(image_base64)
                part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
                contents[-1].parts.append(part)

            if override_tools is not None:
                tools = override_tools
            else:
                native_tools = get_maya_tools()
                mcp_tools = await mcp_service.get_available_tools()
                tools = native_tools + mcp_tools

            tools = convert_tools_to_gemini_tools(tools)

            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.7,
                tools=tools if tools else None,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=True
                )
            )
            fallbacks = [
                'gemini-3.5-flash',
                'gemini-3.1-flash-lite',
                'gemini-2.5-flash-lite',
                'gemini-2.5-flash',
                'gemini-2.0-flash',
                'gemini-1.5-flash',
            ]
            models_to_try = [self._resolve_primary_model(model_tier)]
            for m in fallbacks:
                if m not in models_to_try:
                    models_to_try.append(m)
            response = None
            last_error = None
            available_models = fallback_manager.get_available_models(models_to_try)

            for model in available_models:
                try:
                    response = await self.client.aio.models.generate_content(
                        model=model,
                        contents=contents,
                        config=config
                    )
                    fallback_manager.mark_success(model)
                    break
                except Exception as e:
                    logger.warning(f"Failed generate_content with model {model} ({e}). Trying fallback...")
                    fallback_manager.mark_failed(model, str(e))
                    last_error = e
            
            if response is None:
                if last_error:
                    raise last_error
                raise Exception("Failed to generate response with all models.")
            
            if response.function_calls:
                # Handle single function call in non-streaming mode
                fc = response.function_calls[0]
                return f"TOOL_CALL:{fc.name}:{fc.args}"
            
            # Simple fallback for tools for now (simulated)
            return response.text if response.text else "Done."
        except Exception as e:
            logger.error(f"Gemini API Error: {e}")
            return "I'm sorry, I encountered an error while processing that."

    async def generate_stream(self, context: list[dict], prompt: str, image_base64: str = None, override_tools: list = None, model_tier: str = None) -> AsyncGenerator[str, None]:
        if not hasattr(self, "api_key") or not self.api_key:
            yield "I am missing my API key. Please configure it in Settings."
            return
            
        if self.api_provider != "gemini":
            tools_to_use = override_tools if override_tools is not None else get_maya_tools()
            async for chunk in self.generate_custom_stream(context, tools_to_use):
                yield chunk
            return
            
        context = clean_context(context)
        try:
            contents = []
            system_instruction = None
            for msg in context:
                if msg["role"] == "system":
                    system_instruction = (
                        f"{system_instruction}\n\n{msg['content']}"
                        if system_instruction
                        else msg["content"]
                    )
                    continue
                
                if msg["role"] == "function":
                    part = types.Part.from_function_response(name=msg.get("name", "tool"), response={"result": msg["content"]})
                    target_role = "user"
                elif msg["role"] == "tool_call":
                    fc = types.FunctionCall(name=msg.get("name", "tool"), args=msg.get("args", {}))
                    part = types.Part(function_call=fc, thought_signature=msg.get("thought_signature"))
                    target_role = "model"
                else:
                    part = types.Part.from_text(text=msg["content"])
                    target_role = "user" if msg["role"] == "user" else "model"
                
                if contents and contents[-1].role == target_role:
                    contents[-1].parts.append(part)
                else:
                    contents.append(types.Content(role=target_role, parts=[part]))
            
            # If vision context is provided, attach it to the final user message
            if image_base64 and len(contents) > 0 and contents[-1].role == "user":
                import base64
                image_bytes = base64.b64decode(image_base64)
                part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
                contents[-1].parts.append(part)

            if override_tools is not None:
                tools = override_tools
            else:
                native_tools = get_maya_tools()
                mcp_tools = await mcp_service.get_available_tools()
                tools = native_tools + mcp_tools

            tools = convert_tools_to_gemini_tools(tools)
                
            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.7,
                tools=tools if tools else None,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=True
                )
            )

            fallbacks = [
                'gemini-3.5-flash',
                'gemini-3.1-flash-lite',
                'gemini-2.5-flash-lite',
                'gemini-2.5-flash',
                'gemini-2.0-flash',
                'gemini-1.5-flash',
            ]
            models_to_try = [self._resolve_primary_model(model_tier)]
            for m in fallbacks:
                if m not in models_to_try:
                    models_to_try.append(m)
            stream_started = False
            last_error = None
            current_contents = contents  # May be cleaned per-attempt
            
            available_models = fallback_manager.get_available_models(models_to_try)
            
            for model in available_models:
                try:
                    generator = await self.client.aio.models.generate_content_stream(
                        model=model,
                        contents=current_contents,
                        config=config
                    )
                    fallback_manager.mark_success(model)
                    think_stripper = ThinkStripper()
                    async for chunk in generator:
                        stream_started = True
                        if chunk.text:
                            visible = think_stripper.feed(chunk.text)
                            if visible:
                                yield visible
                        
                        yielded_tc = False
                        if chunk.candidates:
                            for candidate in chunk.candidates:
                                if candidate.content and candidate.content.parts:
                                    for part in candidate.content.parts:
                                        if part.function_call:
                                            yield {
                                                "type": "tool_call",
                                                "name": part.function_call.name,
                                                "args": part.function_call.args,
                                                "thought_signature": getattr(part, "thought_signature", None)
                                            }
                                            yielded_tc = True
                        
                        if not yielded_tc and chunk.function_calls:
                            for fc in chunk.function_calls:
                                yield {
                                    "type": "tool_call",
                                    "name": fc.name,
                                    "args": fc.args
                                }
                    # Emit any text held back by the think-stripper at stream end.
                    tail = think_stripper.flush()
                    if tail:
                        yield tail
                    break
                except Exception as e:
                    err_str = str(e)
                    logger.warning(f"Failed generate_content_stream with model {model} (started={stream_started}): {e}")
                    if not stream_started:
                        fallback_manager.mark_failed(model, err_str)
                    last_error = e
                    if stream_started:
                        break
                    # 400 INVALID_ARGUMENT = orphaned function_call in history
                    # Strip trailing tool_call/function pairs and retry with clean history
                    if "400" in err_str and "INVALID_ARGUMENT" in err_str or "function call turn" in err_str:
                        cleaned = list(current_contents)
                        # Remove trailing model turns that contain function_calls
                        while cleaned and cleaned[-1].role == "model":
                            has_fc = any(getattr(p, "function_call", None) for p in (cleaned[-1].parts or []))
                            if has_fc:
                                cleaned.pop()
                                # Also remove the paired user function_response turn if present
                                if cleaned and cleaned[-1].role == "user":
                                    has_fr = any(getattr(p, "function_response", None) for p in (cleaned[-1].parts or []))
                                    if has_fr:
                                        cleaned.pop()
                            else:
                                break
                        if cleaned != current_contents:
                            logger.info(f"Cleaned orphaned function_call from history for fallback model {model}. Retrying...")
                            current_contents = cleaned
            else:
                if not stream_started and last_error:
                    raise last_error
        except Exception as e:
            logger.error(f"Gemini API Stream Error: {e}")
            yield " I'm sorry, I encountered an error while thinking."

gemini_adapter = GeminiAdapter()
fallback_manager.register_probe_callback(gemini_adapter.probe_model)
