import logging
import json
import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import AsyncGenerator, Union
from ..providers.gemini_adapter import gemini_adapter
from .agent_defs import AGENTS, ROUTING_PROMPT, compose_os_prompt
from ..gemini.function_calls import get_maya_tools
from .tool_router import (
    select_relevant_tools,
    ROUTER_SIZE_GATE,
    _SEND_INTENT_RE,
    _FILE_INTENT_RE,
)
from .intent_parsing import (
    _DIRECT_APP_OPEN_PATTERNS,
    _DIRECT_APP_CLOSE_PATTERNS,
    _DIRECT_APP_FOCUS_PATTERNS,
    _DIRECT_APP_BLOCKERS,
    _OS_BT_RE,
    _OS_WIFI_RE,
    _is_followup_modifier,
    is_generic_youtube_video_query,
    parse_foreground_youtube_play_intent,
    parse_youtube_mode_answer,
    _parse_direct_os_action,
    _format_direct_os_response,
    is_whatsapp_ui_intent,
)
from .execution_policy import (
    adaptive_tool_round_limit,
    build_execution_brief,
    completion_audit_prompt,
    requires_tool_completion,
)
from ..reasoning.tool_planner import tool_planner
from ..security_filter import sanitizer
from ..language_style import (
    BANGLISH,
    ENGLISH,
    HINDILISH,
    LANGUAGE_STYLES,
    detect_conversation_style,
    detect_language_style,
    response_style_directive,
)

import re

logger = logging.getLogger(__name__)

# Module-level FailureRecord for retry logic — defined here to avoid
# re-defining a class inside the hot tool-execution loop every call.
@dataclass
class FailureRecord:
    attempt: int
    tool: str
    args: dict
    error: str

# Maximum characters for a single tool output to prevent context blowup
MAX_TOOL_OUTPUT_CHARS = 3000

# Tools requiring explicit user approval before execution
DANGER_TOOLS = [
    "execute_python", "execute_powershell", "delete_file",
    "trash_background_email", "permanent_delete_email",
    "configure_gmail_credentials", "send_background_email",
    "manage_system_state", "manage_processes",
    "whatsapp_revoke_message", "close_apps_except", "configure_mcp_server",
]
# The unified `pc` router and `perform_shortcut` dispatch several distinct
# risk levels through the SAME func_name, so a plain func_name-in-DANGER_TOOLS
# check can't see them — each needs an explicit action-aware check instead.
_DANGER_PC_ACTIONS = {"process_kill", "shutdown", "restart", "hibernate", "sleep"}
_DANGER_SHORTCUT_ACTIONS = {"shutdown", "restart", "hibernate", "sleep"}
# The unified `file` tool's deletes are irreversible and (delete_by_name) can hit
# multiple files across all drives, so they must round-trip through the approval
# gate just like shutdown/process_kill. write/move/rename/organize stay
# frictionless — the user relies on those completing without a prompt.
_DANGER_FILE_ACTIONS = {"delete", "delete_by_name"}

_ACTION_ALIASES = {
    # ``perform_shortcut`` accepts this alias for sleep. Canonicalize it before
    # evaluating approval so an alias cannot reach the executor ungated.
    "suspend": "sleep",
}


def _canonical_action(value: object) -> str:
    """Normalize router actions exactly once before any security decision."""
    action = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    return _ACTION_ALIASES.get(action, action)


def _tool_call_requires_approval(
    func_name: str,
    args: dict | None,
    mcp_tool_names=(),
) -> bool:
    """Return whether a tool call must pass the explicit approval gate."""
    args = args if isinstance(args, dict) else {}
    action = _canonical_action(args.get("action"))
    return (
        func_name in DANGER_TOOLS
        or (func_name == "pc" and action in _DANGER_PC_ACTIONS)
        or (func_name == "perform_shortcut" and action in _DANGER_SHORTCUT_ACTIONS)
        or (func_name == "file" and action in _DANGER_FILE_ACTIONS)
        or func_name in mcp_tool_names
    )


# ── Clarification localization ────────────────────────────────────────────────
# Deterministic tool replies (contact lists, not-found) bypass the LLM, so the
# language directive never applies to them. Detect the user's language from
# their message and render from fixed templates in bn / hi / en.

def _detect_user_lang(text: str) -> str:
    return detect_language_style(text)


_CLARIFY_PICK = {
    BANGLISH: "'{query}' diye {n} jon contact pelam. Kake pathabo bolo:\n{items}\nNumber bole dao (jemon '1 number ta') ba exact naam bolo.",
    HINDILISH: "'{query}' se {n} contact mile. Kise bheju batao:\n{items}\nNumber bata do (jaise '1 number wala') ya exact naam bolo.",
    ENGLISH: "I found {n} contacts matching '{query}'. Which one should I send it to?\n{items}\nReply with the number (e.g. '1') or the exact name.",
}

_CLARIFY_NOT_FOUND = {
    BANGLISH: "'{name}' name kono contact khuje pelam na. {detail}",
    HINDILISH: "'{name}' naam ka koi contact nahi mila. {detail}",
    ENGLISH: "I couldn't find any contact named '{name}'. {detail}",
}

_NOT_FOUND_DETAIL = {
    "not_connected": {
        BANGLISH: "WhatsApp service ekhono connect hoyni - ektu por abar bolo.",
        HINDILISH: "WhatsApp service abhi connect nahi hui - thodi der baad phir bolo.",
        ENGLISH: "WhatsApp isn't connected yet - please try again in a minute.",
    },
    "not_found": {
        BANGLISH: "Banan ta ektu onnobhabe bole dekho, ba direct number diye bolo (jemon: 'WhatsApp e 919933148570 e hi pathao').",
        HINDILISH: "Naam thodi alag spelling se bolo, ya seedha number de do (jaise: 'WhatsApp pe 919933148570 pe hi bhejo').",
        ENGLISH: "Try a slightly different spelling, or give me the number directly (e.g. 'send hi to 919933148570 on WhatsApp').",
    },
}

# Deterministic YouTube fast-path replies — same per-style template pattern.
_YT_TITLE_REQUEST = {
    BANGLISH: "Kon cinema-ta dekhte chao? Naam ta bolo, ami YouTube e screen e open kore chaliye dibo.",
    HINDILISH: "Kaunsi movie dekhni hai? Naam batao, main YouTube pe screen pe khol ke chala dungi.",
    ENGLISH: "Which movie do you want to watch? Tell me the name and I'll open and play it on YouTube.",
}

_YT_MODE_REQUEST = {
    BANGLISH: "'{query}' ta kivabe chalabo? Screen e dekhbe naki background e sudhu sunbe? 🎵",
    HINDILISH: "'{query}' kaise chalau? Screen pe dekhoge ya background me sirf sunoge? 🎵",
    ENGLISH: "How should I play '{query}'? Watch it on screen, or just listen in the background? 🎵",
}

_YT_FG_SUCCESS = {
    BANGLISH: "YouTube e '{query}' screen e open kore chaliye dilam.",
    HINDILISH: "YouTube pe '{query}' screen pe khol ke chala diya.",
    ENGLISH: "Opened and playing '{query}' on YouTube on screen.",
}

_YT_FG_PARTIAL = {
    BANGLISH: "YouTube e '{query}' open hoyeche, kintu foreground playback fully confirm korte parini: {result}",
    HINDILISH: "YouTube pe '{query}' khul gaya, lekin foreground playback fully confirm nahi kar payi: {result}",
    ENGLISH: "Opened '{query}' on YouTube, but couldn't fully confirm foreground playback: {result}",
}

_YT_FG_FAILED = {
    BANGLISH: "YouTube e '{query}' chaliye dite parlam na: {result}",
    HINDILISH: "YouTube pe '{query}' chala nahi payi: {result}",
    ENGLISH: "Couldn't play '{query}' on YouTube: {result}",
}

_YT_BG_SUCCESS = {
    BANGLISH: "'{query}' background e chaliye dilam. 🎵 Bondho korte chaile bolo.",
    HINDILISH: "'{query}' background me chala diya. 🎵 Band karna ho to bolo.",
    ENGLISH: "Playing '{query}' in the background. 🎵 Just tell me when you want it stopped.",
}

_YT_BG_FAILED = {
    BANGLISH: "'{query}' background e chalate parlam na: {result}",
    HINDILISH: "'{query}' background me chala nahi payi: {result}",
    ENGLISH: "Couldn't play '{query}' in the background: {result}",
}


def _style_msg(templates: dict, style: str, **kwargs) -> str:
    tpl = templates.get(style if style in LANGUAGE_STYLES else ENGLISH) or templates[ENGLISH]
    return tpl.format(**kwargs)


def _format_clarification(
    payload_str: str,
    user_text: str,
    style: str | None = None,
) -> str:
    """Render a CLARIFICATION_NEEDED tool payload in the user's language."""
    lang = style if style in LANGUAGE_STYLES else _detect_user_lang(user_text)
    try:
        p = json.loads(payload_str)
    except Exception:
        # Legacy plain-text payload: relay everything after the first line
        return payload_str.split("\n", 1)[-1].strip() or payload_str
    kind = p.get("kind")
    if kind == "contact_pick":
        cands = p.get("candidates", [])
        items = "\n".join(
            f"{i}. {c.get('name', '?')} — {c.get('number', '?')}"
            for i, c in enumerate(cands, start=1)
        )
        return _CLARIFY_PICK[lang].format(query=p.get("query", ""), n=len(cands), items=items)
    if kind == "contact_not_found":
        detail = _NOT_FOUND_DETAIL.get(p.get("reason", "not_found"), _NOT_FOUND_DETAIL["not_found"])[lang]
        return _CLARIFY_NOT_FOUND[lang].format(name=p.get("name", "?"), detail=detail)
    return payload_str


def _is_pref_true(key: str, default: bool = True) -> bool:
    """Read a boolean UserPreferences value. Returns `default` if missing or unreadable."""
    from ...database.connection import SessionLocal
    from ...database.preferences import read_bool_pref

    db = SessionLocal()
    try:
        return read_bool_pref(db, key, default)
    except Exception as exc:
        logger.warning(f"[agent_team] Failed to read preference {key}: {exc}")
    finally:
        db.close()
    return default


def _declared_tool_names(tool) -> tuple[str, ...]:
    """Return function names exposed by a native or provider-neutral tool."""
    native_name = getattr(tool, "__name__", None)
    if native_name:
        return (str(native_name),)
    if not isinstance(tool, dict):
        return ()
    if tool.get("type") == "function":
        name = (tool.get("function") or {}).get("name")
    else:
        name = tool.get("name")
    return (str(name),) if name else ()


def _merge_mcp_tool_schemas(
    native_tools: list,
    mcp_tools: list,
    *,
    max_total: int,
) -> list:
    """Append unique MCP schemas without exceeding the provider tool budget."""
    merged = list(native_tools)
    seen_names = {
        name
        for tool in merged
        for name in _declared_tool_names(tool)
    }

    for tool in mcp_tools:
        names = _declared_tool_names(tool)
        if not names or any(name in seen_names for name in names):
            continue
        if len(merged) >= max_total:
            break
        merged.append(tool)
        seen_names.update(names)

    return merged


async def _summarize_completed_actions(agent_name: str, agent_context: list, agent_tool_history: list, task_text: str) -> str:
    """When the agent uses all allowed tool rounds, generate a concise final
    summary from the tool results instead of showing a vague failure banner."""
    from ..providers.gemini_adapter import ThinkStripper

    summary_context = agent_context + agent_tool_history + [{
        "role": "user",
        "content": (
            "You have reached the maximum number of tool rounds. "
            "Using the tool results above, write a concise, user-facing summary "
            "of what was completed. If something failed, say so briefly. "
            "Do not ask follow-up questions and do not call any tools."
        )
    }]
    try:
        raw = await gemini_adapter.generate_response(summary_context, None)
        cleaned = ThinkStripper.clean_full(raw).strip()
        return cleaned or f"[{agent_name}] Task completed after all allowed rounds."
    except Exception as exc:
        logger.warning(f"[{agent_name}] Final summary generation failed: {exc}")
        return f"[{agent_name}] Task completed after all allowed rounds."


# ── Fast keyword-based router (avoids Gemini API call) ───────────────────────
# Patterns that ALWAYS go to OS_EXECUTOR — no LLM needed
_OS_PATTERNS = re.compile(
    r"(whatsapp|whatapp|whatsap|watsapp|telegram|email|mail|gmail|youtube|chrome|open |start |launch |close |volume|brightness"
    r"|screenshot|screen|type |click|trash|delete|send |send.*message|forward|pathao|pathiye|patha|পাঠা|bhej|vej|chalao|chalu|bondho|kholo|khulo|khul|khol"
    r"|download|install|reminder|schedule|contact|save|recall|forget|skill|mcp|mode.*change"
    r"|professional mode|friendly mode|coding mode|clipboard|process|app "
    r"|select |profile|switch |scroll|press |minimize|maximize|window|browser"
    r"|play |pause|stop |mute|unmute|tab |shortcut|hotkey|drag|resize"
    r"|notif|alarm|timer|khulje|khulte|chalao|band koro|kholo|khulo|dekho|snapshot"
    r"|bluetooth|blutooth|blootooth|ব্লুটুথ|wi-?fi|wifi|ওয়াইফাই"
    # System power/status controls (lock/shutdown/restart/sleep/hibernate/battery)
    # previously fell through to the Gemini router, which risks misclassifying a
    # status QUESTION ("battery koto ache?") as chit-chat/CHAT — same failure
    # mode as the original bluetooth bug. Keep these tight (whole-word-ish) to
    # avoid false positives on unrelated names/words.
    r"|\block\b|লক|shut ?down|বন্ধ করে দাও|\brestart\b|রিস্টার্ট|\breboot\b"
    r"|\bhibernate\b|sleep mode|pc.{0,4}sleep|laptop.{0,4}sleep"
    r"|\bbattery\b|ব্যাটারি|charge koto|\bstats?\b|cpu usage|ram usage|system stats)",
    re.IGNORECASE
)
# Patterns that ALWAYS go to RESEARCHER
_RESEARCH_PATTERNS = re.compile(
    r"(search|খুজ|খোঁজ|news|khabor|khobor|khobar|খবর|latest|current|today.*news|find online|google it"
    r"|what is|who is|weather|stock|price of)",
    re.IGNORECASE
)
# "Strong" research signals — an unambiguous web-lookup intent. Used to tell a
# real research query apart from a bare "what is/who is" that is actually a
# device-status question (see _OS_STATUS_RE below).
_STRONG_RESEARCH_PATTERNS = re.compile(
    r"(search|খুজ|খোঁজ|news|khabor|khobor|khobar|খবর|latest|current|today.*news"
    r"|find online|google|weather|stock|price of)",
    re.IGNORECASE
)
# Pure device/system status words — "what is my battery %" / "what is CPU usage"
# match both research ("what is") and OS ("battery"), but need no web search.
_TODAY_NEWS_VARIANT_RE = re.compile(
    r"\b(?:ajker|aajker|today(?:'s)?)\b.{0,80}\bnew\s+ta\b",
    re.IGNORECASE,
)

_OS_STATUS_RE = re.compile(
    r"\b(battery|charge|cpu|ram|memory|disk|stats?|status|volume|brightness|clipboard)\b",
    re.IGNORECASE,
)
# Patterns that ALWAYS go to CHAT (canvas/widget requests — never CODER)
_CODER_PATTERNS = re.compile(
    r"(write.*code|code.*likh|script|python file|run.*\.py|debug|fix.*bug"
    r"|create.*file|edit.*file|read.*file|file.*poro|terminal|powershell"
    r"|project.*create|repo|test.*run)",
    re.IGNORECASE
)

_CANVAS_PATTERNS = re.compile(
    r"(tracker|widget|dashboard|kanban|habit.*track|to.?do|todo|planner|calculator|game banao"
    r"|ui banao|banao.*game|interactive|canvas|visualization|chart banao|design koro"
    r"|create.*app|build.*app|make.*app|ekta.*banao|\bbana.{0,20}\bde\b|ekta.*tool)",
    re.IGNORECASE
)

_GREETING_PATTERNS = re.compile(
    r"^(hi|hii|hello|hey|yo|maya|hi maya|hello maya|hey maya|namaste|nomoskar|salaam"
    r"|good morning|good afternoon|good evening|good night|kemon acho|ki khobor|kaise ho)$",
    re.IGNORECASE
)

# App-control gates, follow-up detection, and deterministic OS-control parsing
# now live in intent_parsing.py (pure, hermetically testable) and are imported
# above.

# Last primary agent per session — lets a short follow-up ("50% koro" after
# "volume 20% koro") stick to the same agent instead of being misread as chat.
# Bounded LRU: on a long-running process, old sessions are evicted so this
# never grows unbounded (leak-safe). Newest session stays at the end.
_LAST_AGENT_MAX_SESSIONS = 500
_LAST_AGENT_BY_SESSION: "OrderedDict[str, str]" = OrderedDict()
_LAST_DIRECT_APP_BY_SESSION: "OrderedDict[str, str]" = OrderedDict()
# Kept as a no-op compatibility symbol for older integrations/tests. Runtime
# follow-up state is exclusively stored in _LAST_DIRECT_APP_BY_SESSION.
_LAST_DIRECT_APP_NAME: str | None = None


def _remember_last_agent(session_id: str, agent: str) -> None:
    """Record the session's primary agent, evicting the oldest past the cap."""
    if session_id in _LAST_AGENT_BY_SESSION:
        _LAST_AGENT_BY_SESSION.move_to_end(session_id)
    _LAST_AGENT_BY_SESSION[session_id] = agent
    while len(_LAST_AGENT_BY_SESSION) > _LAST_AGENT_MAX_SESSIONS:
        _LAST_AGENT_BY_SESSION.popitem(last=False)


def _remember_direct_app(session_id: str, app_name: str | None) -> None:
    if not app_name:
        _LAST_DIRECT_APP_BY_SESSION.pop(session_id, None)
        return
    if session_id in _LAST_DIRECT_APP_BY_SESSION:
        _LAST_DIRECT_APP_BY_SESSION.move_to_end(session_id)
    _LAST_DIRECT_APP_BY_SESSION[session_id] = app_name
    while len(_LAST_DIRECT_APP_BY_SESSION) > _LAST_AGENT_MAX_SESSIONS:
        _LAST_DIRECT_APP_BY_SESSION.popitem(last=False)


# Last deterministic OS control per session ("volume"/"brightness"), so a bare
# follow-up ("50% koro") knows which control to nudge. Same bounded-LRU as above.
_LAST_OS_CONTROL_BY_SESSION: "OrderedDict[str, str]" = OrderedDict()


def _remember_os_control(session_id: str, control: str | None) -> None:
    """Record the session's last OS control type (None = leave unchanged)."""
    if not control:
        return
    if session_id in _LAST_OS_CONTROL_BY_SESSION:
        _LAST_OS_CONTROL_BY_SESSION.move_to_end(session_id)
    _LAST_OS_CONTROL_BY_SESSION[session_id] = control
    while len(_LAST_OS_CONTROL_BY_SESSION) > _LAST_AGENT_MAX_SESSIONS:
        _LAST_OS_CONTROL_BY_SESSION.popitem(last=False)


# Sessions where a send flow stopped mid-way to ask the user for missing input
# (unknown contact number, missing message text, pick-a-contact clarification).
# The next reply usually carries JUST that info ("Likho je valo achis",
# "9876543210") with zero routable keywords — without this flag it falls to the
# short-message CHAT branch or the Gemini router, both of which misread it as
# chit-chat and strand the flow on CHAT (no messaging tools). One-shot: popped
# by the next routing decision, re-armed only while the flow is clearly alive.
# Same bounded-LRU pattern as above.
_PENDING_SEND_BY_SESSION: "OrderedDict[str, bool]" = OrderedDict()
_PENDING_YOUTUBE_TITLE_BY_SESSION: "OrderedDict[str, bool]" = OrderedDict()
# Session → query awaiting a "screen e dekhbo naki background e shunbo?" answer.
# Armed when a YouTube play request names WHAT to play but not HOW; the next
# turn's mode answer dispatches to search_youtube (visible) or
# play_youtube_background (audio-only VLC).
_PENDING_YOUTUBE_MODE_BY_SESSION: "OrderedDict[str, str]" = OrderedDict()

# Tools that EXECUTE a send (the message actually leaves the machine) vs. tools
# that merely progress a send flow (contact lookup/save). Used to decide whether
# a send conversation is still pending after a turn.
_SEND_EXECUTING_TOOLS = {
    "whatsapp_send_message", "whatsapp_send_file", "whatsapp_send_multiple_files",
    "whatsapp_ui_send_message", "whatsapp_call", "send_background_email",
}
_SEND_FLOW_TOOLS = _SEND_EXECUTING_TOOLS | {
    "get_contact_number", "save_contact", "read_whatsapp_chat",
}


def _delivery_fingerprint(tool_name: str, args: dict) -> str:
    """Stable key used to prevent a model from sending the same payload twice."""
    try:
        payload = json.dumps(args, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    except (TypeError, ValueError):
        payload = repr(args)
    return f"{tool_name}:{payload}"


def _remember_pending_send(session_id: str) -> None:
    """Mark the session's send flow as awaiting the user's next reply."""
    if session_id in _PENDING_SEND_BY_SESSION:
        _PENDING_SEND_BY_SESSION.move_to_end(session_id)
    _PENDING_SEND_BY_SESSION[session_id] = True
    while len(_PENDING_SEND_BY_SESSION) > _LAST_AGENT_MAX_SESSIONS:
        _PENDING_SEND_BY_SESSION.popitem(last=False)


def _remember_pending_youtube_title(session_id: str, style: str = None) -> None:
    """Mark a session as awaiting the title requested for visible YouTube playback.

    Stores the asking turn's conversation style: the title reply itself ("Bangla
    best cinema") usually carries no style markers, so without this the
    confirmation would silently flip to English mid-conversation.
    """
    if session_id in _PENDING_YOUTUBE_TITLE_BY_SESSION:
        _PENDING_YOUTUBE_TITLE_BY_SESSION.move_to_end(session_id)
    _PENDING_YOUTUBE_TITLE_BY_SESSION[session_id] = style or ENGLISH
    while len(_PENDING_YOUTUBE_TITLE_BY_SESSION) > _LAST_AGENT_MAX_SESSIONS:
        _PENDING_YOUTUBE_TITLE_BY_SESSION.popitem(last=False)


def _remember_pending_youtube_mode(session_id: str, query: str) -> None:
    """Mark a session as awaiting the screen/background answer for `query`."""
    if session_id in _PENDING_YOUTUBE_MODE_BY_SESSION:
        _PENDING_YOUTUBE_MODE_BY_SESSION.move_to_end(session_id)
    _PENDING_YOUTUBE_MODE_BY_SESSION[session_id] = query
    while len(_PENDING_YOUTUBE_MODE_BY_SESSION) > _LAST_AGENT_MAX_SESSIONS:
        _PENDING_YOUTUBE_MODE_BY_SESSION.popitem(last=False)


def evict_session_state(session_id: str) -> None:
    """Remove all ephemeral routing/follow-up state for one session."""
    _LAST_AGENT_BY_SESSION.pop(session_id, None)
    _LAST_DIRECT_APP_BY_SESSION.pop(session_id, None)
    _LAST_OS_CONTROL_BY_SESSION.pop(session_id, None)
    _PENDING_SEND_BY_SESSION.pop(session_id, None)
    _PENDING_YOUTUBE_TITLE_BY_SESSION.pop(session_id, None)
    _PENDING_YOUTUBE_MODE_BY_SESSION.pop(session_id, None)


def _previous_user_messages(context_history: list, current_text: str, n: int = 1) -> list:
    """Up to `n` prior user messages (chronological), excluding the current one."""
    out = []
    current = (current_text or "").strip()
    for msg in reversed(context_history or []):
        if msg.get("role") != "user":
            continue
        content = (msg.get("content") or "").strip()
        if not content or content == current:
            continue
        out.append(content)
        if len(out) >= n:
            break
    return list(reversed(out))


def _router_context_prefix(context_history: list, current_text: str) -> str:
    """A tiny hint of the last turn so the LLM router can resolve follow-ups."""
    prevs = _previous_user_messages(context_history, current_text, n=1)
    if not prevs:
        return ""
    return (
        "[Recent context — the new request may be a follow-up to this]\n"
        f"Previous user message: {prevs[-1][:160]}\n\n"
    )


_ANCHOR_MAX_WORDS = 6


def _carries_tool_signal(text: str) -> bool:
    """True if the message alone gives the tool router something to rank on:
    an explicit send/file/OS keyword, or enough words for semantic ranking."""
    t = text or ""
    if _SEND_INTENT_RE.search(t) or _FILE_INTENT_RE.search(t) or _OS_PATTERNS.search(t):
        return True
    return len(t.split()) > _ANCHOR_MAX_WORDS


def _tool_router_query(text: str, context_history: list) -> str:
    """Query used to rank tools. A short mid-flow reply ("50% koro", a bare
    phone number, "je ami valo achi") carries no tool signal of its own, so
    prepend the most recent user message that does ("volume 20% koro",
    "Pintu ke hi send kor") — otherwise ranking starves the very tools the
    flow needs and the agent announces it can't do the task.

    Walks back past intermediate signal-less turns so a chain of follow-ups
    ("volume 20 koro" -> "50 koro" -> "70 koro") still carries the keyword,
    not just the previous (also-bare) turn."""
    if _carries_tool_signal(text):
        return text
    prevs = _previous_user_messages(context_history, text, n=5)
    if not prevs:
        return text
    # Prefer the most recent message that itself carries real signal.
    anchor = next(
        (p for p in reversed(prevs) if _carries_tool_signal(p)),
        prevs[-1],
    )
    return f"{anchor} {text}"


def _last_app_from_history(
    context_history: list[dict],
    session_id: str | None = None,
) -> str | None:
    for msg in reversed(context_history):
        if msg.get("role") != "tool_call":
            continue
        if msg.get("name") not in {"open_app", "focus_app"}:
            continue
        args = msg.get("args") or {}
        app_name = args.get("app_name")
        if app_name:
            return str(app_name)
    return _LAST_DIRECT_APP_BY_SESSION.get(session_id) if session_id else None


_BULK_APP_WORDS_RE = re.compile(
    r"\b(all|every(?:thing)?|rest|baki|sob|shob|ja\s+ja)\b|সব|বাকি|যা\s+যা",
    re.IGNORECASE,
)
_APP_EXCEPT_BEFORE_RE = re.compile(
    r"^\s*(?P<apps>.+?)\s+(?:baad|bad)\s+(?:diye|die)\b|"
    # Standalone exception markers that need no trailing "diye": the bare
    # "bade"/"baade" (বাদে) and "chara"/"chhara" (ছাড়া). Without "bade" here,
    # "vs code bade sob app close" fell through to close_app("vs code bade
    # sob") and was refused as a protected process.
    r"^\s*(?P<apps_chara>.+?)\s+(?:chara|chhara|bade|baade|ছাড়া|বাদে|বাদ\s+দিয়ে)\b",
    re.IGNORECASE,
)
_APP_EXCEPT_AFTER_RE = re.compile(
    r"\b(?:except|excluding|keep)\s+(?P<apps>.+?)"
    r"(?=\s+\b(?:open|all|everything|rest|baki|sob|shob|close|bondho|band|koro)\b|$)",
    re.IGNORECASE,
)


def _parse_bulk_app_close(text: str) -> str | None:
    """Detect a broad "close every app" request and any app(s) to keep open.

    Returns:
      None         → not a bulk-close request (let single-app parsing handle it)
      ""           → close ALL apps, no exception ("close all apps")
      "<name>"     → close all apps EXCEPT the named one(s) ("... except vs code")

    Without the no-exception branch, "close all apps" fell through to
    close_app("all") — which hunted for a process literally named "all" and
    errored — instead of the broad close-all path.
    """
    if not _DIRECT_APP_CLOSE_PATTERNS.search(text) or not _BULK_APP_WORDS_RE.search(text):
        return None
    match = _APP_EXCEPT_BEFORE_RE.search(text) or _APP_EXCEPT_AFTER_RE.search(text)
    if not match:
        return ""  # bulk word + close, but no "except X" → close everything
    excluded = next((value for value in match.groupdict().values() if value), "")
    return excluded.strip(" ,.-")


def _parse_direct_app_action(text: str, fallback_app_name: str | None = None) -> tuple[str, str] | None:
    """
    Deterministic fast path for simple app control.
    This avoids spending an LLM call just to decide open_app("notepad").
    """
    if _DIRECT_APP_BLOCKERS.search(text):
        return None
    # Bluetooth/WiFi are OS controls handled by the direct OS path (pc router),
    # not apps — "bluetooth chalu koro" must never become open_app("bluetooth").
    if _OS_BT_RE.search(text) or _OS_WIFI_RE.search(text):
        return None

    bulk_excluded = _parse_bulk_app_close(text)
    if bulk_excluded is not None:
        return "close_apps_except", bulk_excluded

    from ...tools.desktop.apps import _is_safe_app_query, _normalize_app_query

    if not _is_safe_app_query(text):
        return None

    app_name = _normalize_app_query(text)
    if not app_name and fallback_app_name:
        if _DIRECT_APP_CLOSE_PATTERNS.search(text):
            return "close_app", fallback_app_name
        if _DIRECT_APP_FOCUS_PATTERNS.search(text):
            return "focus_app", fallback_app_name
    if not app_name and _DIRECT_APP_CLOSE_PATTERNS.search(text):
        return "close_active_window", "active window"

    if not app_name:
        return None
    if len(app_name.split()) > 4:
        return None

    if _DIRECT_APP_CLOSE_PATTERNS.search(text):
        return "close_app", app_name
    if _DIRECT_APP_FOCUS_PATTERNS.search(text):
        return "focus_app", app_name
    if _DIRECT_APP_OPEN_PATTERNS.search(text):
        return "open_app", app_name
    return None


def _format_direct_app_response(func_name: str, app_name: str, result: str) -> str:
    result_lower = result.lower()
    if result.startswith("SUCCESS"):
        if func_name == "close_apps_except":
            # app_name is empty for a plain "close all apps" (no exception).
            if not app_name:
                if "protected maya/runtime windows kept open" in result_lower:
                    return (
                        "Sob app close kore dilam. "
                        "Protected Maya/runtime window open rekhechi."
                    )
                return "Sob app close kore dilam."
            if "protected maya/runtime windows kept open" in result_lower:
                return (
                    f"{app_name} open rekhe baki safe app gulo close kore dilam. "
                    "Protected Maya/runtime window open rekhechi."
                )
            return f"{app_name} open rekhe baki app gulo close kore dilam."
        if "browser fallback" in result_lower:
            return f"{app_name} native app paini, tai browser e open korlam."
        if "windows search" in result_lower:
            return f"{app_name} Windows Search diye open korar try korlam."
        if func_name == "close_app":
            return f"{app_name} close kore dilam."
        if func_name == "close_active_window":
            return "active window close kore dilam."
        if func_name == "focus_app":
            return f"{app_name} focus kore dilam."
        return f"{app_name} open kore dilam."
    return f"{app_name} er kaj korte parlam na: {result}"


def _fast_route(
    text: str, last_agent: str | None = None, pending_send: bool = False
) -> list[str] | None:
    """Returns agent list instantly from keywords, or None to fall back to Gemini router."""
    t = text.lower()

    is_canvas = bool(_CANVAS_PATTERNS.search(t))
    is_os = bool(_OS_PATTERNS.search(t))
    is_research = bool(
        _RESEARCH_PATTERNS.search(t) or _TODAY_NEWS_VARIANT_RE.search(t)
    )
    is_coder = bool(_CODER_PATTERNS.search(t))

    # Canvas/widget requests always go to CHAT before file/code routing.
    if is_canvas:
        return ["CHAT"]

    # Common compound tasks should run as a pipeline, not collapse to one agent.
    if is_research and is_coder and is_os:
        return ["RESEARCHER", "CODER", "OS_EXECUTOR"]
    if is_research and is_os:
        # Device-status question ("what is my battery %") matches both, but the
        # only research signal is a generic "what is/who is" and it's really an
        # OS status query — skip the wasteful web-search hop, go straight to OS.
        if not (
            _STRONG_RESEARCH_PATTERNS.search(t) or _TODAY_NEWS_VARIANT_RE.search(t)
        ) and _OS_STATUS_RE.search(t):
            return ["OS_EXECUTOR"]
        return ["RESEARCHER", "OS_EXECUTOR"]
    if is_research and is_coder:
        return ["RESEARCHER", "CODER"]

    # Ambiguous multi-intent commands are better handled by the LLM router.
    if sum([is_os, is_research, is_coder]) > 1:
        return None

    if is_os:
        return ["OS_EXECUTOR"]
    if is_research:
        return ["RESEARCHER"]
    if is_coder:
        return ["CODER"]

    # A send flow paused mid-way (Maya asked for the contact number, the
    # message text, or a pick-from-list clarification): the next turn usually
    # supplies JUST that info ("Likho je valo achis", "9876543210") with zero
    # routable keywords. Stick to OS_EXECUTOR so the flow keeps its messaging
    # tools — the short-message branch below and the Gemini router both
    # misread such replies as chit-chat and strand the flow on CHAT, which
    # has no WhatsApp tools at all. Explicit new intents above still win.
    if pending_send:
        return ["OS_EXECUTOR"]

    # Follow-up modifier continuing the previous OS action (e.g. "50% koro" or
    # "aro barao" after "volume 20% koro"). Stick to OS_EXECUTOR — this both
    # fixes the misroute-to-CHAT and skips a Gemini router call (quota-friendly).
    if last_agent == "OS_EXECUTOR" and _is_followup_modifier(t):
        return ["OS_EXECUTOR"]

    # Only route very short messages to CHAT instantly (≤3 words, no question words).
    # Greetings first; if not a greeting but still a short, non-question fragment,
    # treat it as conversational filler and send to CHAT too (saves quota).
    words = text.split()
    if len(words) <= 3:
        if _GREETING_PATTERNS.search(t.strip()):
            return ["CHAT"]
        if not any(c in t for c in ["?", "কি", "কেন", "কোথায়", "কখন", "what", "why", "how", "where"]):
            return ["CHAT"]
    return None  # ambiguous → use Gemini router
# ─────────────────────────────────────────────────────────────────────────────


_IST = timezone(timedelta(hours=5, minutes=30))


def _render_time_block() -> str:
    """IST clock block for the system prompt. Computed ONCE per request and
    reused across every tool-round, so the system-instruction prefix stays
    byte-identical — that lets Gemini's implicit prefix caching actually hit.
    (A per-second timestamp here busted the cache on every round.) Minute
    precision: the value is 'request start' and already approximate, so false
    seconds precision buys nothing."""
    now = datetime.now(_IST)
    return (
        f"\n\nCURRENT DATE & TIME (India Standard Time — IST / UTC+5:30):"
        f"\n- Date   : {now.strftime('%A, %d %B %Y')}"
        f"\n- Time   : {now.strftime('%I:%M %p')} IST"
        f"\n- 24hr   : {now.strftime('%H:%M')}"
        f"\nIf the user asks about the current time, date, day, or year, use ONLY these values. Do NOT guess or use training data dates."
    )


def _build_agent_context(
    agent_config,
    base_history: list[dict],
    previous_results: list[str],
    original_task: str,
    active_mode: str,
    active_tone: str,
    time_block: str,
    conversation_style: str,
    execution_brief: str = "",
) -> list[dict]:
    """
    Builds a clean context for a sub-agent.
    - Only user/assistant turns from base_history (no tool_call/function roles)
    - Injects previous agent results as a user context message
    - Appends the original task as the final user turn
    """
    tone_directive = (
        f"\nACTIVE MODE: {active_mode.upper()}\nTONE CONTEXT: {active_tone}"
        f"\n{response_style_directive(conversation_style)}"
    )
    if active_mode == "friendly":
        tone_directive += (
            "\nSince active mode is FRIENDLY/SASSY, your personality is:"
            "\n- Smart, witty, sarcastic, mildly dramatic, and very funny."
            "\n- You are NOT a girlfriend, but you ARE a friend. Do NOT use সোনা, বাবু, জানু, লক্ষ্মীটি."
            "\n- If someone asks who created or made you, you must say: Nirupam made me."
            "\n- Keep the mandatory per-turn RESPONSE STYLE above even when a tool returns English data. Translate conversational text without changing technical values."
            "\n- Be confident and sarcastic but ALWAYS complete the task."
            "\n- Example tone: 'Arre yaar, itna simple kaam — chalo karte hain!'"
        )
    else:
        tone_directive += (
            "\nDo NOT use affectionate companion terms like 'সোনা', 'বাবু', 'জানু', "
            "or 'লক্ষ্মীটি' in this mode. Keep your conversational language normal, polite, or technical."
        )

    # OS_EXECUTOR's manual is large; send only the capability blocks this request
    # needs (compose_os_prompt falls back to the full prompt on no match). Other
    # agents use their static prompt unchanged.
    if agent_config.name == "OS_EXECUTOR":
        base_prompt = compose_os_prompt(original_task)
    else:
        base_prompt = agent_config.system_prompt
    # time_block is rendered once per request and passed in, so this prefix is
    # identical across tool-rounds (keeps implicit prefix caching alive).
    system_instruction = f"{base_prompt}\n{tone_directive}{time_block}"

    summary_messages = [
        message
        for message in base_history
        if message.get("role") == "system"
        and (
            message.get("_maya_context_summary")
            or str(message.get("content", "")).startswith("[Conversation Summary")
        )
    ]
    if summary_messages:
        system_instruction += "\n\n" + summary_messages[-1]["content"]

    # Clean history: user/assistant roles only. The rolling summary above holds
    # older turns, while this short verbatim tail keeps current intent precise.
    clean_history = [
        m for m in base_history if m.get("role") in ("user", "assistant")
    ]
    trimmed = clean_history[-5:] if len(clean_history) > 5 else clean_history

    context = [{"role": "system", "content": system_instruction}] + trimmed

    task_with_plan = original_task
    if execution_brief:
        task_with_plan = f"{execution_brief}\n\n[Original user request]\n{original_task}"

    # Inject results from previous agents as context
    if previous_results:
        combined = "\n\n---\n".join(previous_results)
        context.append({
            "role": "user",
            "content": (
                f"[Context from previous agents]\n{combined}\n\n"
                f"[Your task]\n{task_with_plan}"
            )
        })
    else:
        context.append({"role": "user", "content": task_with_plan})

    return context


async def _run_tool(func_name: str, args: dict, all_tools: list) -> str:
    """Execute a single tool call and return the result as a string."""
    func = next(
        (t for t in all_tools if hasattr(t, "__name__") and t.__name__ == func_name),
        None
    )
    if not func:
        if "__" in func_name:
            try:
                from ...tools.mcp_service import mcp_service
                result = await mcp_service.call_tool(func_name, args or {})
                return str(result)
            except Exception as e:
                return f"MCP tool '{func_name}' raised an error: {e}"
        return f"Tool '{func_name}' is disabled or not available."
    try:
        import inspect
        if inspect.iscoroutinefunction(func):
            result = await func(**args)
        else:
            result = func(**args)
        return str(result)
    except Exception as e:
        return f"Tool '{func_name}' raised an error: {e}"


async def _log_fast_path(
    session_id: str,
    text: str,
    intent_class: str,
    tool_name: str = "",
    error: str = None,
    latency_ms: int = 0,
) -> None:
    """
    Log a fast-path (non-LLM) request to Observability.
    Called from: Sentinel block, direct OS, direct app paths.
    Swallows all exceptions — never let metrics logging break the main flow.
    """
    try:
        from datetime import datetime, timezone
        from ...system.observability import observability, RequestMetrics
        await observability.log(RequestMetrics(
            timestamp=datetime.now(timezone.utc).isoformat(),
            session_id=session_id,
            intent_class=intent_class,
            tokens_input=len(text) // 4,
            tokens_output=0,
            latency_ms=latency_ms,
            model_used="none",
            model_version="none",
            model_tier="fast",
            tool_calls=[tool_name] if tool_name else [],
            verifier_retries=0,
            fast_path_hit=True,
            error=error,
        ))
    except Exception:
        pass  # Observability is never allowed to crash the main flow


async def execute_workflow(
    session_id: str,
    text: str,
    context_history: list[dict],
    image_base64: str = None
) -> AsyncGenerator[Union[str, dict], None]:
    """
    Stateful execution coordinator for the Multi-Agent team.
    Routes tasks to agents, runs specialized execution loops,
    and passes inter-agent results downstream.
    """
    logger.info(f"Multi-agent workflow routing request: {text}")
    conversation_style = detect_conversation_style(text, context_history)
    if text.startswith("SYSTEM_EVENT_STARTUP_GREETING"):
        conversation_style = BANGLISH

    # ── Phase A: Intent Sentinel (Security Layer) ────────────────────────────
    from .intent_sentinel import IntentSentinel
    from ...system.state_manager import state_manager
    ctx_prompt_info = state_manager.get_prompt_context()
    active_mode = ctx_prompt_info.get("mode_name", "professional")
    capabilities = ctx_prompt_info.get("capabilities", [])

    intent_decision = IntentSentinel.evaluate(text, active_mode, capabilities)
    if intent_decision.status == "block":
        await _log_fast_path(session_id, text, "sentinel_block", error=intent_decision.reason)
        yield intent_decision.suggested_action or intent_decision.reason
        return
    # NOTE: IntentSentinel never returns "needs_approval" — it has no way to
    # pause and resume a turn, so that verdict was a dead end (see
    # intent_sentinel.py). The real approval gate for shutdown/restart/etc.
    # is the DANGER_TOOLS check further down this file, which properly
    # round-trips through a tool_call_request approve/deny event.

    # ── Phase B: Analysis Pass + BudgetManager ────────────────────────────────
    from ..reasoning.analysis_pass import run_heuristic_pass, build_task_graph_if_needed
    from ..budget_manager import budget_manager

    analysis_result = run_heuristic_pass(text, context_history)
    analysis_result = await build_task_graph_if_needed(analysis_result, text, context_history)

    # Register the intended tier with BudgetManager — it may downgrade silently
    # if this session has already exceeded its budget. The downgrade message (if
    # any) is surfaced inline below so the user always knows.
    budget_manager.set_requested_tier(session_id, analysis_result.model_tier)

    # The tier actually in force for this turn — may be lower than requested
    # if a prior turn in this session already downgraded it. This is what
    # gets passed to the main reasoning call below so the tier genuinely
    # picks the model instead of just being logged.
    active_tier = budget_manager.get_active_tier(session_id)

    # Emit downgrade notification if budget was previously exceeded
    downgrade_msg = budget_manager.pop_downgrade_notification(session_id)
    if downgrade_msg:
        yield downgrade_msg

    execution_graph = (
        analysis_result.task_graph
        if analysis_result.needs_task_graph and isinstance(analysis_result.task_graph, dict)
        else None
    )
    execution_brief = build_execution_brief(execution_graph, text)
    if execution_brief:
        step_count = len(execution_graph.get("tasks", []))
        logger.info(
            "[AgentTeam] Prepared adaptive plan with %s steps; "
            "continuing through the full tool-capable agent loop.",
            step_count,
        )
        yield {
            "type": "agent_status",
            "data": {
                "active_agent": "Planner",
                "status": f"Prepared {step_count}-step adaptive plan.",
                "loop_count": 0,
            },
        }

    # ── 1. Routing phase ─────────────────────────────────────────────────────
    # Try fast keyword router first (saves ~1-2s Gemini call). Pass the last
    # agent so short follow-ups can stick to it instead of collapsing to CHAT,
    # and the one-shot pending-send flag so a mid-send clarification reply
    # ("Likho je valo achis") continues on OS_EXECUTOR instead of CHAT.
    pending_send = _PENDING_SEND_BY_SESSION.pop(session_id, None) is not None
    _pending_yt_style = _PENDING_YOUTUBE_TITLE_BY_SESSION.pop(session_id, None)
    pending_youtube_title = _pending_yt_style is not None
    if pending_youtube_title and _pending_yt_style in LANGUAGE_STYLES:
        # The title reply ("Bangla best cinema") carries no style markers of its
        # own — keep the style the question was asked in, don't flip to English.
        conversation_style = _pending_yt_style
    if not pending_youtube_title and not image_base64 and text.strip():
        # The in-memory flag can be lost (backend restart, or the title
        # question was asked by the LLM loop instead of the deterministic
        # gate). Re-derive it from history: if the PREVIOUS user message was
        # a generic visible-YouTube request ("yt te cinema chaliye dao") and
        # this reply carries no other tool signal, treat it as the awaited
        # title — otherwise the ≤3-word branch strands it on CHAT, which has
        # no YouTube tools, and Maya falsely claims the tool is missing.
        _prevs = _previous_user_messages(context_history, text, n=1)
        _cancelish = re.search(
            r"\b(na|thak|cancel|bad|dorkar|lagbe na|stop|bondho)\b", text, re.IGNORECASE
        )
        if _prevs and not _carries_tool_signal(text) and not _cancelish:
            _prev_yt_q = parse_foreground_youtube_play_intent(_prevs[-1])
            if _prev_yt_q and is_generic_youtube_video_query(_prev_yt_q):
                pending_youtube_title = True
                # Same style-continuity rule as the stored-flag path: the reply
                # is just a title, so inherit the asking turn's style.
                _prev_style = detect_conversation_style(_prevs[-1], context_history)
                if _prev_style in LANGUAGE_STYLES:
                    conversation_style = _prev_style
    last_direct_app = _last_app_from_history(context_history, session_id)
    direct_app_candidate = (
        _parse_direct_app_action(text, last_direct_app)
        if not image_base64
        else None
    )
    youtube_request_query = (
        parse_foreground_youtube_play_intent(text)
        if not image_base64
        else None
    )
    youtube_title_needed = is_generic_youtube_video_query(youtube_request_query)
    # HOW should it play? "dekhbo/video" → visible screen; "shunbo/background"
    # → VLC audio. A YT play request naming WHAT but not HOW must be confirmed
    # first so audio never pops a browser window and vice versa.
    pending_youtube_mode_query = (
        _PENDING_YOUTUBE_MODE_BY_SESSION.pop(session_id, None)
        if not image_base64
        else None
    )
    youtube_mode = parse_youtube_mode_answer(text) if not image_base64 else None
    youtube_mode_needed_query = None
    background_youtube_query = None
    foreground_youtube_query = None
    if pending_youtube_title and not image_base64 and text.strip():
        # Reply carries the awaited title; the original request was a
        # watch-worded one (cinema/movie/video) so visible playback is right.
        foreground_youtube_query = text.strip()
    elif pending_youtube_mode_query:
        if youtube_mode == "background":
            background_youtube_query = pending_youtube_mode_query
        elif youtube_mode == "foreground":
            foreground_youtube_query = pending_youtube_mode_query
        # else: answer names no mode (maybe a topic change) → normal routing.
    elif youtube_request_query and not youtube_title_needed:
        if youtube_mode == "background":
            background_youtube_query = youtube_request_query
        elif youtube_mode == "foreground":
            foreground_youtube_query = youtube_request_query
        else:
            youtube_mode_needed_query = youtube_request_query
    # A syntactically complete app command is more authoritative than keyword
    # routing. In particular, a one-word follow-up such as "Close" used to hit
    # the short-chat branch before the remembered app could be consulted, making
    # Maya incorrectly claim it lacked the required tool. Route these commands
    # straight to the deterministic app executor instead.
    agents_to_run = (
        ["OS_EXECUTOR"]
        if youtube_title_needed or foreground_youtube_query
        or background_youtube_query or youtube_mode_needed_query
        or direct_app_candidate
        else _fast_route(
            text, _LAST_AGENT_BY_SESSION.get(session_id), pending_send=pending_send
        )
    )
    if agents_to_run:
        logger.info(f"Router response (fast-route): {agents_to_run}")
    else:
        # Fall back to Gemini router for ambiguous messages. Prepend a hint of the
        # recent turn so follow-ups ("50% koro" after "volume 20% koro") resolve.
        ctx_prefix = _router_context_prefix(context_history, text)
        routing_context = [
            {"role": "system", "content": ROUTING_PROMPT},
            {"role": "user", "content": f"{ctx_prefix}Request: {text}"}
        ]
        routing_response = ""
        try:
            routing_response = await gemini_adapter.generate_response(
                routing_context, f"{ctx_prefix}Request: {text}", override_tools=[]
            )
            logger.info(f"Router response (gemini): {routing_response}")

            cleaned_resp = routing_response.strip()
            if "```" in cleaned_resp:
                cleaned_resp = cleaned_resp.split("```")[1]
                if cleaned_resp.startswith("json"):
                    cleaned_resp = cleaned_resp[4:]
                cleaned_resp = cleaned_resp.strip()

            parsed = json.loads(cleaned_resp)
            agents_to_run = parsed.get("agents", [])
        except Exception as e:
            logger.warning(f"Failed to parse agent routing JSON. Error: {e}")
            agents_to_run = []
            if routing_response:
                for agent_name in ["RESEARCHER", "CODER", "OS_EXECUTOR"]:
                    if agent_name in routing_response.upper():
                        agents_to_run.append(agent_name)

    cleaned_agents = []
    for agent in agents_to_run:
        upper = agent.upper()
        if upper in AGENTS and upper not in cleaned_agents:
            cleaned_agents.append(upper)

    if not cleaned_agents:
        cleaned_agents = ["CHAT"]

    logger.info(f"Target agents scheduled in order: {cleaned_agents}")

    # Remember the primary agent so the NEXT turn's follow-up can stick to it.
    _remember_last_agent(session_id, cleaned_agents[-1])

    direct_app_action = (
        direct_app_candidate
        if cleaned_agents == ["OS_EXECUTOR"] and not image_base64
        else None
    )
    direct_youtube_query = (
        foreground_youtube_query
        if cleaned_agents == ["OS_EXECUTOR"] and not image_base64
        else None
    )
    direct_youtube_bg_query = (
        background_youtube_query
        if cleaned_agents == ["OS_EXECUTOR"] and not image_base64
        else None
    )
    if direct_app_action and not _is_pref_true("PERM_SYSTEM"):
        direct_app_action = None
    if direct_youtube_query and not _is_pref_true("PERM_SYSTEM"):
        direct_youtube_query = None
    if direct_youtube_bg_query and not _is_pref_true("PERM_SYSTEM"):
        direct_youtube_bg_query = None
    if youtube_mode_needed_query and cleaned_agents == ["OS_EXECUTOR"]:
        # WHAT to play is known, HOW is not — confirm before touching anything.
        _remember_pending_youtube_mode(session_id, youtube_mode_needed_query)
        final_text = _style_msg(
            _YT_MODE_REQUEST, conversation_style, query=youtube_mode_needed_query
        )
        context_history.append({"role": "assistant", "content": final_text})
        await _log_fast_path(
            session_id,
            text,
            "youtube_mode_request",
        )
        yield final_text
        return
    if direct_youtube_bg_query:
        logger.info(
            "Direct background YouTube playback matched: %r",
            direct_youtube_bg_query,
        )
        yield {
            "type": "agent_status",
            "data": {
                "active_agent": AGENTS["OS_EXECUTOR"].role,
                "status": "Playing in the background...",
                "loop_count": 0,
            },
        }

        from ...tools.desktop.advanced.youtube_player import play_youtube_background

        try:
            raw_result = play_youtube_background(direct_youtube_bg_query)
        except Exception as exc:
            logger.exception("[DIRECT_YOUTUBE_BG] Background playback failed")
            raw_result = f"ERROR: Background playback failed unexpectedly: {exc}"

        safe_result = sanitizer.sanitize_tool_output("play_youtube_background", raw_result)
        context_history.append({
            "role": "tool_call",
            "name": "play_youtube_background",
            "args": {"query": direct_youtube_bg_query},
        })
        context_history.append({
            "role": "function",
            "name": "play_youtube_background",
            "content": str(safe_result),
        })

        if str(safe_result).startswith("SUCCESS"):
            final_text = _style_msg(
                _YT_BG_SUCCESS, conversation_style, query=direct_youtube_bg_query
            )
        else:
            final_text = _style_msg(
                _YT_BG_FAILED, conversation_style,
                query=direct_youtube_bg_query, result=safe_result,
            )

        context_history.append({"role": "assistant", "content": final_text})
        await _log_fast_path(
            session_id,
            text,
            "background_youtube",
            tool_name="play_youtube_background",
            error=None if str(safe_result).startswith("SUCCESS") else str(safe_result).split(":", 1)[0],
        )
        yield final_text
        return
    if youtube_title_needed:
        _remember_pending_youtube_title(session_id, conversation_style)
        final_text = _style_msg(_YT_TITLE_REQUEST, conversation_style)
        context_history.append({"role": "assistant", "content": final_text})
        await _log_fast_path(
            session_id,
            text,
            "youtube_title_request",
        )
        yield final_text
        return
    if direct_youtube_query:
        logger.info(
            "Direct foreground YouTube playback matched: %r",
            direct_youtube_query,
        )
        yield {
            "type": "agent_status",
            "data": {
                "active_agent": AGENTS["OS_EXECUTOR"].role,
                "status": "Opening YouTube in the foreground...",
                "loop_count": 0,
            },
        }

        from ...tools.desktop.advanced.browser_tools import search_youtube

        try:
            raw_result = search_youtube(direct_youtube_query)
        except Exception as exc:
            logger.exception("[DIRECT_YOUTUBE] Foreground playback failed")
            raw_result = f"ERROR: YouTube playback failed unexpectedly: {exc}"

        safe_result = sanitizer.sanitize_tool_output("search_youtube", raw_result)
        context_history.append({
            "role": "tool_call",
            "name": "search_youtube",
            "args": {"query": direct_youtube_query},
        })
        context_history.append({
            "role": "function",
            "name": "search_youtube",
            "content": str(safe_result),
        })

        if str(safe_result).startswith("SUCCESS"):
            final_text = _style_msg(
                _YT_FG_SUCCESS, conversation_style, query=direct_youtube_query
            )
        elif str(safe_result).startswith(("PARTIAL", "INFO")):
            final_text = _style_msg(
                _YT_FG_PARTIAL, conversation_style,
                query=direct_youtube_query, result=safe_result,
            )
        else:
            final_text = _style_msg(
                _YT_FG_FAILED, conversation_style,
                query=direct_youtube_query, result=safe_result,
            )

        context_history.append({"role": "assistant", "content": final_text})
        await _log_fast_path(
            session_id,
            text,
            "foreground_youtube",
            tool_name="search_youtube",
            error=None if str(safe_result).startswith("SUCCESS") else str(safe_result).split(":", 1)[0],
        )
        yield final_text
        return
    if direct_app_action:
        func_name, app_name = direct_app_action
        logger.info(f"Direct app action matched: {func_name}({app_name!r})")

        yield {
            "type": "agent_status",
            "data": {
                "active_agent": AGENTS["OS_EXECUTOR"].role,
                "status": "Executing local app action...",
                "loop_count": 0,
            },
        }

        tool_args = (
            {"excluded_apps": app_name}
            if func_name == "close_apps_except"
            else {"app_name": app_name}
        )
        if func_name == "close_apps_except":
            req = tool_planner.queue_tool(func_name, tool_args, risk_level="danger")
            yield {"type": "tool_call_request", "data": req}
            try:
                approved = await asyncio.wait_for(
                    tool_planner.wait_for_approval(req["request_id"]),
                    timeout=300.0,
                )
            except asyncio.TimeoutError:
                approved = False
                logger.warning("[DIRECT_APP] Approval timeout for close_apps_except")
            if not approved:
                denial = "Permission denied: broad app close was not approved."
                context_history.append(
                    {"role": "tool_call", "name": func_name, "args": tool_args}
                )
                context_history.append(
                    {"role": "function", "name": func_name, "content": denial}
                )
                final_text = "Approval na paoway baki app gulo close kora hoyni."
                context_history.append({"role": "assistant", "content": final_text})
                await _log_fast_path(
                    session_id,
                    text,
                    "direct_app",
                    tool_name=func_name,
                    error="APPROVAL_DENIED",
                )
                yield final_text
                return

        if func_name == "close_apps_except":
            from ...tools.desktop.apps import close_apps_except as app_func
        elif func_name == "close_app":
            _SONG_NAMES = {
                # English
                "song", "songta", "song ti", "songti", "songe", "music", "miusic", "audio",
                "sound", "media", "playback", "melody", "tune",
                # Bangla
                "গান", "গানটা", "গানটি", "সুর", "সঙ্গীত", "গীত", "গীতা",
                "বাদ্য", "বাজনা", "আওয়াজ", "শব্দ",
                # Banglish
                "gaan", "gan", "gaanta", "sur", "sor", "songeet", "sangeet", "geet", "bajna",
                "awaj", "awaz", "shobdo",
            }
            if app_name and any(w in _SONG_NAMES for w in app_name.lower().split()):
                from ...tools.desktop.advanced.youtube_player import stop_youtube_background

                raw_result = stop_youtube_background()
                safe_result = sanitizer.sanitize_tool_output("stop_youtube_background", raw_result)
                logger.info(f"[DIRECT_OS] stop_youtube_background result: {str(safe_result)[:200]}")

                context_history.append({"role": "tool_call", "name": "stop_youtube_background", "args": {}})
                context_history.append({"role": "function", "name": "stop_youtube_background", "content": str(safe_result)})

                if str(safe_result).startswith("SUCCESS"):
                    final_text = "গান band kore dilam."
                else:
                    final_text = f"গান bondho korte parlam na: {raw_result}"

                context_history.append({"role": "assistant", "content": final_text})
                yield final_text
                return

            from ...tools.desktop.apps import close_app as app_func
        elif func_name == "close_active_window":
            from ...tools.desktop.apps import close_active_window as active_close

            app_func = lambda _app_name: active_close()
        elif func_name == "focus_app":
            from ...tools.desktop.apps import focus_app as app_func
        else:
            from ...tools.desktop.apps import open_app as app_func

        started_at = asyncio.get_running_loop().time()
        try:
            raw_result = app_func(app_name)
        except Exception as exc:
            logger.exception(
                "[DIRECT_APP] Tool '%s' raised unexpectedly",
                func_name,
            )
            raw_result = f"ERROR: App action failed unexpectedly: {exc}"
        safe_result = sanitizer.sanitize_tool_output(func_name, raw_result)
        logger.info(f"[DIRECT_OS] Tool '{func_name}' result: {str(safe_result)[:200]}")

        context_history.append({
            "role": "tool_call",
            "name": func_name,
            "args": tool_args,
        })
        context_history.append({
            "role": "function",
            "name": func_name,
            "content": str(safe_result),
        })

        final_text = _format_direct_app_response(func_name, app_name, str(safe_result))
        if str(safe_result).startswith("SUCCESS"):
            if func_name in {"open_app", "focus_app"}:
                _remember_direct_app(session_id, app_name)
            elif (
                func_name == "close_app"
                and _LAST_DIRECT_APP_BY_SESSION.get(session_id) == app_name
            ):
                _remember_direct_app(session_id, None)
        context_history.append({"role": "assistant", "content": final_text})
        result_text = str(safe_result).lstrip()
        result_status = result_text.split(":", 1)[0].upper()
        error_status = (
            None
            if result_status in {"SUCCESS", "OK"}
            else result_status[:40] or "UNKNOWN_FAILURE"
        )
        elapsed_ms = int(
            (asyncio.get_running_loop().time() - started_at) * 1000
        )
        await _log_fast_path(
            session_id,
            text,
            "direct_app",
            tool_name=func_name,
            error=error_status,
            latency_ms=elapsed_ms,
        )
        yield final_text
        return

    # ── WhatsApp explicit UI-send fast path detection ─────────────────────────
    # If the user says "WhatsApp open kore X find kore ... send koro", we want
    # the OS_EXECUTOR to drive the real WhatsApp Desktop app via
    # whatsapp_ui_send_message rather than the background Baileys service.
    whatsapp_ui_intent = (
        cleaned_agents == ["OS_EXECUTOR"]
        and not image_base64
        and is_whatsapp_ui_intent(text)
    )

    # ── Deterministic zero-LLM controls (volume / brightness / mute / clipboard) ──
    # Same idea as the direct app path: skip the whole LLM loop for simple laptop
    # controls — instant, free, more reliable.
    direct_os_action = (
        _parse_direct_os_action(text, _LAST_OS_CONTROL_BY_SESSION.get(session_id))
        if cleaned_agents == ["OS_EXECUTOR"] and not image_base64 and not whatsapp_ui_intent
        else None
    )
    # The zero-LLM OS fast path must respect PERM_SYSTEM just like the LLM tool
    # filter does. If the user disabled system controls, force the request onto
    # the LLM path (where the tools themselves are filtered out anyway).
    if direct_os_action and not _is_pref_true("PERM_SYSTEM"):
        direct_os_action = None
    if direct_os_action:
        func_name, kwargs, control_type, display_msg = direct_os_action
        logger.info(f"Direct OS action matched: {func_name}({kwargs})")

        yield {
            "type": "agent_status",
            "data": {
                "active_agent": AGENTS["OS_EXECUTOR"].role,
                "status": "Executing local control...",
                "loop_count": 0,
            },
        }

        is_danger = _tool_call_requires_approval(func_name, kwargs)
        if is_danger:
            req = tool_planner.queue_tool(func_name, kwargs, risk_level="danger")
            yield {"type": "tool_call_request", "data": req}
            try:
                approved = await asyncio.wait_for(
                    tool_planner.wait_for_approval(req["request_id"]),
                    timeout=300.0,
                )
            except asyncio.TimeoutError:
                approved = False
                logger.warning(
                    "[DIRECT_OS] Approval timeout for %s(%s). Auto-denying.",
                    func_name,
                    kwargs,
                )
            if not approved:
                denial = "Permission denied: user did not approve this power action."
                context_history.append({"role": "tool_call", "name": func_name, "args": kwargs})
                context_history.append({"role": "function", "name": func_name, "content": denial})
                final_text = "Approval না পাওয়ায় power command execute করা হয়নি।"
                context_history.append({"role": "assistant", "content": final_text})
                yield final_text
                return

        os_func = None
        if func_name == "change_volume":
            from ...tools.desktop.advanced.system_tools import change_volume as os_func
        elif func_name == "read_clipboard":
            from ...tools.desktop.advanced.system_tools import read_clipboard as os_func
        elif func_name == "control_brightness":
            from ...tools.desktop.shortcuts import control_brightness as os_func
        elif func_name == "perform_shortcut":
            from ...tools.desktop.shortcuts import perform_shortcut as os_func
        elif func_name == "pc":
            from ...tools.unified import pc as os_func

        if os_func is not None:
            try:
                raw_result = os_func(**kwargs)
            except Exception as exc:
                raw_result = f"ERROR: {exc}"
            safe_result = sanitizer.sanitize_tool_output(func_name, raw_result)
            logger.info(f"[DIRECT_OS] Tool '{func_name}' result: {str(safe_result)[:200]}")

            context_history.append({"role": "tool_call", "name": func_name, "args": kwargs})
            context_history.append({"role": "function", "name": func_name, "content": str(safe_result)})

            _remember_os_control(session_id, control_type)
            final_text = _format_direct_os_response(func_name, str(safe_result), display_msg)
            context_history.append({"role": "assistant", "content": final_text})
            await _log_fast_path(session_id, text, "direct_os", tool_name=func_name)
            yield final_text
            return

    total_agents = len(cleaned_agents)

    # ── 2. Sequential execution phase ────────────────────────────────────────
    all_tools = get_maya_tools()
    mcp_tools = []
    try:
        from ...tools.mcp_service import MAX_GEMINI_TOOLS, mcp_service

        # Fetch once per workflow. Native relevance routing below reduces the
        # active schema set first; MCP schemas then consume the remaining budget.
        mcp_tools = await mcp_service.get_available_tools(limit=MAX_GEMINI_TOOLS)
    except Exception as exc:
        logger.warning("[AgentTeam] MCP discovery unavailable: %s", exc)
    # MCP tools are external capabilities. Their schemas do not provide a
    # trustworthy risk contract, so every discovered MCP call needs an explicit
    # approval bound to its exact server, tool, and arguments.
    mcp_tool_names = {
        name
        for tool in mcp_tools
        for name in _declared_tool_names(tool)
    }

    previous_agent_results: list[str] = []  # Carries results between agents
    # Send-flow tracking for the pending-send continuation memory (see below):
    # did any tool actually execute a send this request, and did any tool at
    # least progress a send flow (contact lookup/save)?
    send_executed = False
    send_flow_touched = False
    executed_delivery_fingerprints: set[str] = set()
    # Render the clock once per request; every round reuses it so the system
    # prefix stays byte-identical and Gemini's implicit caching can hit.
    request_time_block = _render_time_block()

    for agent_idx, agent_name in enumerate(cleaned_agents):
        is_last_agent = (agent_idx == len(cleaned_agents) - 1)
        agent_config = AGENTS[agent_name]
        logger.info(f"Activating agent: {agent_config.name}")

        # Get tone/mode from StateManager
        from ...system.state_manager import state_manager
        ctx_prompt_info = state_manager.get_prompt_context()
        active_tone = ctx_prompt_info.get("tone", "")
        active_mode = ctx_prompt_info.get("mode_name", "professional")

        # Fetch dynamic tool names to ensure they aren't filtered out
        from ...skills.skill_watcher import get_dynamic_tools
        dynamic_tool_names = {t.__name__ for t in get_dynamic_tools() if hasattr(t, "__name__")}

        # Filter tools for this specific agent (allow dynamic skills for all active agents)
        override_tools = [
            t for t in all_tools
            if hasattr(t, "__name__") and (
                t.__name__ in agent_config.tool_names or
                t.__name__ in dynamic_tool_names
            )
        ]

        # MCP APIs belong to OS_EXECUTOR. Merge them into the candidate set BEFORE
        # relevance routing so they are scored against the user request alongside
        # native tools, preventing irrelevant MCP tools (like memory graph) from
        # polluting the active tool set on unrelated turns.
        if agent_name == "OS_EXECUTOR" and mcp_tools:
            from ...tools.mcp_service import TOOL_SAFETY_BUFFER

            before_mcp = len(override_tools)
            override_tools = _merge_mcp_tool_schemas(
                override_tools,
                mcp_tools,
                max_total=MAX_GEMINI_TOOLS - TOOL_SAFETY_BUFFER,
            )
            logger.info(
                "[AgentTeam] Merged %d MCP tool schema(s) into OS_EXECUTOR candidate set.",
                len(override_tools) - before_mcp,
            )

        # ── Dynamic tool routing ──────────────────────────────────────────────
        # Large tool sets (OS_EXECUTOR ~55 native + MCP) are re-sent as function-call
        # schemas on every tool-round. Rank them down to the tools relevant to THIS
        # request via cached embeddings: big token savings + fewer mis-fired
        # calls. Done once per agent activation so the tool set stays stable
        # across rounds. Lean agents (CHAT/CODER/RESEARCHER) fall under the gate
        # and pass through untouched. select_relevant_tools never raises and
        # never empties the set (falls back to all candidates on any weak signal).
        if len(override_tools) > ROUTER_SIZE_GATE:
            _before = len(override_tools)
            _router_query = _tool_router_query(text, context_history)
            if execution_brief:
                # Complex goals often need tools implied by later planned steps,
                # not just words present in the original request. Include the
                # bounded plan so relevance routing keeps those tools available.
                _router_query = f"{_router_query}\n{execution_brief}"
            override_tools = select_relevant_tools(_router_query, override_tools)
            logger.info(
                f"[ToolRouter] {agent_config.name}: {_before} -> "
                f"{len(override_tools)} tools for: {_router_query[:60]!r}"
            )

        # If the user explicitly asked for the WhatsApp Desktop UI flow, make
        # sure the dedicated UI tool is available even after aggressive routing.
        if whatsapp_ui_intent:
            _has_ui_tool = any(
                hasattr(t, "__name__") and t.__name__ == "whatsapp_ui_send_message"
                for t in override_tools
            )
            if not _has_ui_tool:
                _ui_tool = next(
                    (t for t in all_tools if hasattr(t, "__name__") and t.__name__ == "whatsapp_ui_send_message"),
                    None,
                )
                if _ui_tool is not None:
                    override_tools.append(_ui_tool)
            # Remind the agent it MUST use the UI tool, not background send.
            context_history.append({
                "role": "user",
                "content": "USER WANTS THE WHATSAPP DESKTOP UI FLOW. Use whatsapp_ui_send_message(contact_name, message). Do NOT use whatsapp_send_message."
            })

        # Per-agent tool execution history (tool_call + function pairs)
        # This stays local to each agent's execution loop
        agent_tool_history: list[dict] = []

        # Tracks the most recent screenshot captured by a tool (e.g. take_verified_screenshot)
        # This gets injected as a real Vision image into the next Gemini call
        current_agent_screenshot: str = None

        # Complex planned work gets more room than a simple one-shot command,
        # while hard caps in execution_policy prevent runaway loops.
        max_tool_rounds = adaptive_tool_round_limit(
            agent_name,
            analysis_result.complexity_score,
            execution_graph,
        )
        tool_round = 0
        agent_final_text = ""
        tool_completion_required = requires_tool_completion(
            agent_name,
            text,
            has_image=bool(image_base64),
        )
        completion_audit_used = False
        completion_retry_prompt: str | None = None

        yield {
            "type": "agent_status",
            "data": {
                "active_agent": agent_config.role,
                "status": "Starting task...",
                "loop_count": 0
            }
        }

        needs_final_summary = False

        while tool_round <= max_tool_rounds:
                # Build context fresh each round (includes latest tool results)
            agent_context = _build_agent_context(
                agent_config=agent_config,
                base_history=context_history,
                previous_results=previous_agent_results,
                original_task=text,
                active_mode=active_mode,
                active_tone=active_tone,
                time_block=request_time_block,
                conversation_style=conversation_style,
                execution_brief=execution_brief,
            )

            # Append local tool history for this agent
            # (tool_call + function pairs from previous rounds in this agent)
            agent_context.extend(agent_tool_history)

            # After tool execution rounds, Gemini requires a user turn after
            # the function response — append a continue signal so turn order is valid
            if tool_round > 0 and agent_tool_history:
                agent_context.append({
                    "role": "user",
                    "content": "Continue with the task using the tool results above."
                })

            yield {
                "type": "agent_status",
                "data": {
                    "active_agent": agent_config.role,
                    "status": f"Thinking... (round {tool_round + 1})",
                    "loop_count": tool_round
                }
            }

            tool_calls_this_round: list[dict] = []
            text_this_round = ""

            # First round sends the original task. A one-shot completion audit
            # can replace it when an action agent tried to finish without using
            # any tool (which means no real action happened).
            if completion_retry_prompt:
                user_prompt = completion_retry_prompt
                completion_retry_prompt = None
            else:
                user_prompt = text if tool_round == 0 else None
            defer_action_text = (
                is_last_agent
                and tool_completion_required
                and not agent_tool_history
            )
            # Vision context: round 0 uses the original user-provided image (if any).
            # Subsequent rounds use any screenshot that was captured by a tool this round.
            if tool_round == 0:
                image_b64 = image_base64
            elif current_agent_screenshot:
                image_b64 = current_agent_screenshot
                current_agent_screenshot = None  # consume it; reset for next round
            else:
                image_b64 = None

            async for chunk in gemini_adapter.generate_stream(
                agent_context,
                user_prompt,
                image_b64,
                override_tools=override_tools,
                model_tier=active_tier
            ):
                if isinstance(chunk, dict):
                    if chunk.get("type") == "tool_call":
                        tool_calls_this_round.append(chunk)
                    # Always pass through status/reasoning events
                    else:
                        yield chunk
                else:
                    text_this_round += chunk
                    # Only stream text to user from the LAST agent
                    # Intermediate agents' text is buffered (used as context for next agent)
                    if is_last_agent and not defer_action_text:
                        yield chunk

            # ── No tool calls → agent is done ────────────────────────────
            if not tool_calls_this_round:
                if (
                    tool_completion_required
                    and not agent_tool_history
                    and override_tools
                    and not completion_audit_used
                ):
                    completion_audit_used = True
                    completion_retry_prompt = completion_audit_prompt(text)
                    logger.info(
                        "[%s] Tool-free premature completion detected; running one execution audit.",
                        agent_config.name,
                    )
                    yield {
                        "type": "agent_status",
                        "data": {
                            "active_agent": agent_config.role,
                            "status": "Checking execution completeness...",
                            "loop_count": tool_round,
                        },
                    }
                    continue

                # The first action response is buffered until we know whether
                # it actually called a tool. If the audit still cannot execute,
                # surface its precise blocker instead of swallowing the reply.
                if defer_action_text and text_this_round:
                    yield text_this_round
                if text_this_round.strip():
                    agent_final_text = text_this_round.strip()
                    previous_agent_results.append(agent_final_text)
                elif tool_round > 0:
                    # Agent used tools but gave no final text — collect tool outputs as result
                    tool_outputs = [
                        m["content"] for m in agent_tool_history
                        if m.get("role") == "function"
                    ]
                    if tool_outputs:
                        summary = f"[{agent_config.name} completed actions. Results: " + "; ".join(tool_outputs[-3:]) + "]"
                        previous_agent_results.append(summary)
                break

            # ── Process tool calls ────────────────────────────────────────
            yield {
                "type": "agent_status",
                "data": {
                    "active_agent": agent_config.role,
                    "status": f"Executing {len(tool_calls_this_round)} action(s)...",
                    "loop_count": tool_round
                }
            }

            for tc in tool_calls_this_round:
                func_name = tc["name"]
                args = tc.get("args", {})
                delivery_key = _delivery_fingerprint(func_name, args) if func_name in _SEND_EXECUTING_TOOLS else None
                duplicate_delivery = bool(
                    delivery_key and delivery_key in executed_delivery_fingerprints
                )
                if delivery_key and not duplicate_delivery:
                    # A remote acceptance can be lost to a timeout. Do not let a
                    # later model round turn that ambiguity into a second send.
                    executed_delivery_fingerprints.add(delivery_key)

                # ── Safety approval for danger tools ─────────────────
                is_danger = _tool_call_requires_approval(
                    func_name,
                    args,
                    mcp_tool_names,
                )
                approved = not duplicate_delivery
                if is_danger and not duplicate_delivery:
                    from ...database.connection import SessionLocal
                    from ...database.models import UserPreferences
                    from ...database.crypto import crypto_manager

                    db_session = SessionLocal()
                    auto_approve = False
                    try:
                        pref = db_session.query(UserPreferences).filter(
                            UserPreferences.key == "PERM_AUTO_APPROVE"
                        ).first()
                        if pref and pref.value:
                            try:
                                auto_approve = (crypto_manager.decrypt(pref.value) == "true")
                            except Exception:
                                pass
                    finally:
                        db_session.close()

                    req = tool_planner.queue_tool(func_name, args, risk_level="danger")

                    # Auto-approve is a convenience for reversible actions, never
                    # a bypass for destructive or power-control operations.
                    auto_approve_allowed = req.get("risk_level") not in {"HIGH", "CRITICAL"}
                    if auto_approve and auto_approve_allowed:
                        req_copy = dict(req)
                        req_copy["status"] = "executed"
                        yield {"type": "tool_call_request", "data": req_copy}
                        tool_planner.resolve_tool(req["request_id"], approved=True)
                    else:
                        yield {"type": "tool_call_request", "data": req}
                        try:
                            approved = await asyncio.wait_for(
                                tool_planner.wait_for_approval(req["request_id"]),
                                timeout=300.0  # 5 minutes for user to approve
                            )
                        except asyncio.TimeoutError:
                            approved = False
                            logger.warning(f"[agent_team] Approval timeout for {func_name}. Auto-denying.")

                # ── Execute tool ──────────────────────────────────────
                tool_result_verified = False
                if approved:
                    from ...tools.manifest import get_manifest
                    from ...tools.verifier import ResultVerifier, VerifyResult

                    manifest = get_manifest(func_name)
                    # A send with an ambiguous result must not be executed
                    # again automatically; the transport owns safe retries.
                    max_attempts = 1 if func_name in _SEND_EXECUTING_TOOLS else 3
                    failure_history: list[FailureRecord] = []
                    current_tool_name = func_name
                    current_args = args
                    raw_result = None
                    # Initialize verify_result so it's always defined after the loop,
                    # even if max_attempts is ever set to 0 (defensive programming).
                    verify_result = VerifyResult(valid=True)

                    for attempt in range(max_attempts):
                        raw_result = await _run_tool(current_tool_name, current_args, all_tools)
                        verify_result = await ResultVerifier.verify(current_tool_name, raw_result, manifest)

                        if verify_result.valid:
                            break

                        logger.warning(f"Tool {current_tool_name} failed verification (attempt {attempt+1}): {verify_result.reason}")
                        failure_history.append(FailureRecord(
                            attempt=attempt + 1,
                            tool=current_tool_name,
                            args=current_args,
                            error=verify_result.reason
                        ))

                        if not verify_result.retryable:
                            logger.warning(
                                "Tool %s returned a non-retryable failure; preserving the original result.",
                                current_tool_name,
                            )
                            break

                        if attempt < max_attempts - 1:
                            # An approval is bound to the EXACT tool + args the
                            # user saw. A danger tool may retry with identical
                            # args only — replanned args or a fallback tool
                            # would execute something the user never approved
                            # (R06 audit, BUG-022).
                            if is_danger:
                                continue
                            if attempt == 0:
                                # Stage 2: same tool, mini-LLM re-plans args with failure context
                                replan_prompt = (
                                    f"Tool '{current_tool_name}' failed with error: {verify_result.reason}. "
                                    f"Current args: {current_args}. Provide corrected args as JSON."
                                )
                                try:
                                    replan_response = await gemini_adapter.generate_response(agent_context, replan_prompt)
                                    # re is already imported at module top
                                    json_match = re.search(r"```json(.*?)```", replan_response, re.DOTALL)
                                    if json_match:
                                        current_args = json.loads(json_match.group(1).strip())
                                except Exception:
                                    pass  # keep original args if replan fails
                            elif attempt == 1 and manifest.fallback_tool:
                                # Stage 3: switch to fallback tool
                                current_tool_name = manifest.fallback_tool
                                current_args = manifest.adapt_args_for_fallback(failure_history[-1].args)
                                manifest = get_manifest(current_tool_name)

                    if not verify_result.valid and verify_result.retryable:
                        attempts_used = len(failure_history)
                        if func_name in _SEND_EXECUTING_TOOLS:
                            raw_result = (
                                "ERROR: Delivery was not completed. "
                                f"Last error: {verify_result.reason}"
                            )
                        else:
                            raw_result = (
                                f"Failed after {attempts_used} attempt(s). "
                                f"Last error: {verify_result.reason}"
                            )
                    tool_result_verified = verify_result.valid
                elif duplicate_delivery:
                    raw_result = (
                        "ERROR: Duplicate delivery request blocked. "
                        "The earlier delivery result in this request is authoritative."
                    )
                else:
                    raw_result = "Permission denied by user."

                # ── Vision context extraction ─────────────────────────
                # If the tool returned a screenshot (base64), extract it and store
                # so the next Gemini reasoning round receives it as a real image.
                _SCREENSHOT_PREFIX = "SCREENSHOT_BASE64:"
                if isinstance(raw_result, str) and raw_result.startswith(_SCREENSHOT_PREFIX):
                    current_agent_screenshot = raw_result[len(_SCREENSHOT_PREFIX):]
                    raw_result = "[Screenshot captured. Gemini Vision will analyze it in the next reasoning step.]"

                # ── Mode Change Detection ─────────────────────────────────────
                # If the tool returned MODE_CHANGE_TRIGGERED, apply the mode
                # change immediately so the session is cleared and the next
                # agent round (and any subsequent agent) uses the new personality.
                if isinstance(raw_result, str) and "MODE_CHANGE_TRIGGERED:" in raw_result:
                    new_mode = raw_result.split("MODE_CHANGE_TRIGGERED:")[1].strip().split()[0]
                    try:
                        import asyncio as _asyncio
                        _asyncio.create_task(state_manager.change_mode(new_mode))
                    except Exception as _me:
                        logger.warning(f"[agent_team] Inline mode change failed: {_me}")

                # ── System State Detection ────────────────────────────────────
                # If the tool returned SYSTEM_STATE_TRIGGERED, yield it as a
                # text chunk so that both the websocket handler AND the Telegram
                # _process_and_reply can catch it in full_response.
                # Without this, it stays as a tool result the AI sees internally
                # and never surfaces in the streamed text output.
                if isinstance(raw_result, str) and "SYSTEM_STATE_TRIGGERED:" in raw_result:
                    yield raw_result  # surfaces to telegram + websocket handlers
                # ─────────────────────────────────────────────────────────────

                # ── Send-flow tracking ───────────────────────────────────────
                # Feeds the pending-send continuation memory: a send counts as
                # executed only if the send tool actually ran (not denied).
                if func_name in _SEND_FLOW_TOOLS:
                    send_flow_touched = True
                    if tool_result_verified and func_name in _SEND_EXECUTING_TOOLS:
                        send_executed = True

                # ── Clarification short-circuit ──────────────────────────────
                # When a tool needs the user to pick from a list (e.g. multiple
                # WhatsApp contacts matched), relay the list to the user
                # verbatim instead of trusting the LLM to repeat it — weak
                # fallback models paraphrase or drop the list entirely.
                if isinstance(raw_result, str) and raw_result.startswith("CLARIFICATION_NEEDED:"):
                    clarify_text = _format_clarification(
                        raw_result[len("CLARIFICATION_NEEDED:"):].strip(),
                        text,
                        conversation_style,
                    )
                    logger.info(f"[{agent_config.name}] Clarification needed — relaying list to user directly.")
                    # The user's answer ("2", "prothom ta") has no routable
                    # keywords — remember the paused flow so it sticks to
                    # OS_EXECUTOR instead of collapsing to CHAT.
                    _remember_pending_send(session_id)
                    yield f"\n{clarify_text}"
                    previous_agent_results.append(clarify_text)
                    combined = "\n\n".join(r for r in previous_agent_results if r)
                    context_history.append({"role": "assistant", "content": combined})
                    return

                # Sanitize and truncate
                safe_result = sanitizer.sanitize_tool_output(func_name, raw_result)
                if len(str(safe_result)) > MAX_TOOL_OUTPUT_CHARS:
                    safe_result = str(safe_result)[:MAX_TOOL_OUTPUT_CHARS] + "\n... [output truncated]"

                logger.info(f"[{agent_config.name}] Tool '{func_name}' result: {str(safe_result)[:200]}")

                # Append tool_call + function to agent's local history
                # so the next generation round sees the result
                agent_tool_history.append({
                    "role": "tool_call",
                    "name": func_name,
                    "args": args,
                    "thought_signature": tc.get("thought_signature")
                })
                agent_tool_history.append({
                    "role": "function",
                    "name": func_name,
                    "content": str(safe_result)
                })

                # Also record in shared context for memory continuity
                context_history.append({
                    "role": "tool_call",
                    "name": func_name,
                    "args": args,
                    "thought_signature": tc.get("thought_signature")
                })
                context_history.append({
                    "role": "function",
                    "name": func_name,
                    "content": str(safe_result)
                })

                if func_name in _SEND_EXECUTING_TOOLS:
                    # Delivery language comes directly from the observed tool
                    # result. Do not give a fallback model an opportunity to
                    # invent a success or omit an accepted send.
                    delivery_reply = str(safe_result)
                    if not tool_result_verified:
                        _remember_pending_send(session_id)
                    yield f"\n{delivery_reply}"
                    previous_agent_results.append(delivery_reply)
                    context_history.append({"role": "assistant", "content": delivery_reply})
                    return

            tool_round += 1
            if tool_round > max_tool_rounds:
                logger.warning(f"[{agent_config.name}] Max tool rounds reached. Requesting final summary.")
                needs_final_summary = True
                break

        if needs_final_summary:
            final_summary = await _summarize_completed_actions(
                agent_config.name, agent_context, agent_tool_history, text
            )
            if final_summary:
                yield f"\n{final_summary}"
                previous_agent_results.append(final_summary)

    # ── Pending-send continuation memory ─────────────────────────────────────
    # A send-intent turn (or the continuation of one) ran through OS_EXECUTOR
    # but nothing was actually sent — Maya is mid-flow, asking the user for the
    # missing piece (contact number / message text). Remember it so the user's
    # NEXT reply routes back to OS_EXECUTOR with its messaging tools, instead
    # of stranding on CHAT ("আমার টুল লিস্টে WhatsApp নেই" bug). Re-armed from a
    # consumed flag only while the flow is demonstrably alive (a send-flow tool
    # was touched this turn), so an abandoned flow can't pin routing forever.
    if (
        "OS_EXECUTOR" in cleaned_agents
        and not send_executed
        and (_SEND_INTENT_RE.search(text) or (pending_send and send_flow_touched))
    ):
        _remember_pending_send(session_id)

    # ── 3. Persist final assistant message ───────────────────────────────────
    if previous_agent_results:
        combined = "\n\n".join(r for r in previous_agent_results if r)
        context_history.append({"role": "assistant", "content": combined})
