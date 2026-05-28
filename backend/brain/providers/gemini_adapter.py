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
import httpx

logger = logging.getLogger(__name__)

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

def convert_tools_to_openai_tools(tools: list) -> list:
    openai_tools = []
    for func in tools:
        if not hasattr(func, "__name__"):
            continue
        name = func.__name__
        doc = func.__doc__ or ""
        desc = doc.strip().split("\n")[0] if doc else f"Call function {name}"
        
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
            properties[param_name] = {
                "type": param_type,
                "description": f"Parameter {param_name}"
            }
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

class GeminiAdapter(LLMProvider):
    def __init__(self):
        self.client = None
        self.reload_key()
        
    def reload_key(self):
        """Loads key from DB (encrypted), falls back to .env, and configures genai/custom provider."""
        db = SessionLocal()
        try:
            pref = db.query(UserPreferences).filter(UserPreferences.key == "GEMINI_API_KEY").first()
            if pref and pref.value:
                api_key = crypto_manager.decrypt(pref.value)
                logger.info("Loaded Gemini API Key from encrypted database.")
            else:
                api_key = os.getenv("GEMINI_API_KEY")
                if api_key:
                    logger.info("Loaded Gemini API Key from environment.")
                else:
                    logger.warning("No Gemini API Key found. Maya will not be able to respond.")
                    return
            
            # Load stored provider if any
            provider_pref = db.query(UserPreferences).filter(UserPreferences.key == "GEMINI_API_PROVIDER").first()
            stored_provider = None
            if provider_pref and provider_pref.value:
                try:
                    stored_provider = crypto_manager.decrypt(provider_pref.value)
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
            
            # Determine provider
            if stored_provider:
                self.api_provider = stored_provider
            else:
                # Fallback to auto-detection
                if api_key.startswith("sk-or-"):
                    self.api_provider = "openrouter"
                elif api_key.startswith("nvapi-"):
                    self.api_provider = "nvidia"
                elif api_key.startswith("sk-"):
                    if len(api_key) == 67:
                        self.api_provider = "opencode_zen"
                    else:
                        self.api_provider = "openai"
                else:
                    self.api_provider = "gemini"
            
            # Set URL and Model based on selected provider
            if self.api_provider == "openrouter":
                self.api_url = "https://openrouter.ai/api/v1/chat/completions"
                self.model_name = stored_model if stored_model else "google/gemma-4-31b-it:free"
                logger.info("Universal Adapter: Configured for OpenRouter.")
            elif self.api_provider == "nvidia":
                self.api_url = "https://integrate.api.nvidia.com/v1/chat/completions"
                self.model_name = stored_model if stored_model else "meta/llama-3.3-70b-instruct"
                logger.info("Universal Adapter: Configured for NVIDIA NIM.")
            elif self.api_provider == "opencode_zen":
                self.api_url = "https://opencode.ai/zen/v1/chat/completions"
                self.model_name = stored_model if stored_model else "deepseek-v4-flash-free"
                logger.info("Universal Adapter: Configured for OpenCode Zen.")
            elif self.api_provider == "openai":
                self.api_url = "https://api.openai.com/v1/chat/completions"
                self.model_name = stored_model if stored_model else "gpt-4o-mini"
                logger.info("Universal Adapter: Configured for OpenAI.")
            else:
                self.api_provider = "gemini"
                self.api_url = None
                self.model_name = stored_model if stored_model else "gemini-2.5-flash"
                self.client = genai.Client(api_key=api_key)
                logger.info("Universal Adapter: Configured for native Google Gemini API.")
        finally:
            db.close()
            
    async def generate_custom_response(self, context: list[dict], tools: list) -> str:
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
        if self.api_provider == "openrouter":
            for m in ["meta-llama/llama-3.3-70b-instruct:free", "meta-llama/llama-3.2-3b-instruct:free", "deepseek/deepseek-v4-flash:free", "nvidia/nemotron-3-super-120b-a12b:free"]:
                if m not in models_to_try:
                    models_to_try.append(m)
        elif self.api_provider == "opencode_zen":
            # nemotron-3-super-free is the only active working free fallback!
            if self.model_name != "nemotron-3-super-free":
                models_to_try.append("nemotron-3-super-free")
            for m in ["deepseek-v4-flash-free", "nemotron-3-super-free", "qwen3.6-plus-free", "minimax-m2.5-free"]:
                if m not in models_to_try:
                    models_to_try.append(m)
                        
        last_error = None
        for model in models_to_try:
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
                        logger.info(f"Dynamically switching active model to {model} due to fallback success.")
                        self.model_name = model
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
                        
                    return message.get("content", "") or "Done."
            except Exception as e:
                logger.warning(f"Custom LLM API failed with model {model}: {e}")
                last_error = e
                
        if last_error:
            logger.error(f"Custom LLM API Error after trying all models: {last_error}")
        from ...system.state_manager import state_manager
        if state_manager.state.active_mode == "companion":
            return "দুঃখিত সোনা, আমার একটু সমস্যা হচ্ছে।"
        return "I'm sorry, I encountered an error while processing that."

    async def generate_custom_stream(self, context: list[dict], tools: list) -> AsyncGenerator[str, None]:
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
        if self.api_provider == "openrouter":
            for m in ["meta-llama/llama-3.3-70b-instruct:free", "meta-llama/llama-3.2-3b-instruct:free", "deepseek/deepseek-v4-flash:free", "nvidia/nemotron-3-super-120b-a12b:free"]:
                if m not in models_to_try:
                    models_to_try.append(m)
        elif self.api_provider == "opencode_zen":
            # nemotron-3-super-free is the only active working free fallback!
            if self.model_name != "nemotron-3-super-free":
                models_to_try.append("nemotron-3-super-free")
            for m in ["deepseek-v4-flash-free", "nemotron-3-super-free", "qwen3.6-plus-free", "minimax-m2.5-free"]:
                if m not in models_to_try:
                    models_to_try.append(m)
                        
        stream_started = False
        last_error = None
        for model in models_to_try:
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
                async with httpx.AsyncClient() as client:
                    async with client.stream("POST", self.api_url, headers=headers, json=payload, timeout=30.0) as response:
                        response.raise_for_status()
                        if model != self.model_name:
                            logger.info(f"Dynamically switching active model to {model} due to fallback success.")
                            self.model_name = model
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
                                        yield delta["content"]
                                        
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
                if state_manager.state.active_mode == "companion":
                    yield " দুঃখিত সোনা, আমার একটু সমস্যা হচ্ছে।"
                else:
                    yield " I'm sorry, I encountered an error while thinking."
        
    async def generate_response(self, context: list[dict], prompt: str, image_base64: str = None, override_tools: list = None) -> str:
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
                    system_instruction = msg["content"]
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

            tools = override_tools if override_tools is not None else get_maya_tools()
            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.7,
                tools=tools if tools else None,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=True
                )
            )
            models_to_try = [
                'gemini-3.1-flash-lite',
                'gemini-2.5-flash-lite',
                'gemini-2.5-flash',
                'gemini-2.5-pro',
                'gemini-2.0-flash',
                'gemini-3.5-flash',
                'gemini-3.1-pro-preview'
            ]
            response = None
            last_error = None
            for model in models_to_try:
                try:
                    response = await self.client.aio.models.generate_content(
                        model=model,
                        contents=contents,
                        config=config
                    )
                    break
                except Exception as e:
                    logger.warning(f"Failed generate_content with model {model} ({e}). Trying fallback...")
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

    async def generate_stream(self, context: list[dict], prompt: str, image_base64: str = None, override_tools: list = None) -> AsyncGenerator[str, None]:
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
                    system_instruction = msg["content"]
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

            tools = override_tools if override_tools is not None else get_maya_tools()
            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.7,
                tools=tools if tools else None,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=True
                )
            )

            models_to_try = [
                'gemini-3.1-flash-lite',
                'gemini-2.5-flash-lite',
                'gemini-2.5-flash',
                'gemini-2.5-pro',
                'gemini-2.0-flash',
                'gemini-3.5-flash',
                'gemini-3.1-pro-preview'
            ]
            
            stream_started = False
            last_error = None
            current_contents = contents  # May be cleaned per-attempt
            
            for model in models_to_try:
                try:
                    generator = await self.client.aio.models.generate_content_stream(
                        model=model,
                        contents=current_contents,
                        config=config
                    )
                    async for chunk in generator:
                        stream_started = True
                        if chunk.text:
                            yield chunk.text
                        
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
                    break
                except Exception as e:
                    err_str = str(e)
                    logger.warning(f"Failed generate_content_stream with model {model} (started={stream_started}): {e}")
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
