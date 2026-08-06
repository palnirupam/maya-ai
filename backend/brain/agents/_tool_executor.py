import logging
from ..providers.gemini_adapter import gemini_adapter

logger = logging.getLogger(__name__)

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


async def _run_tool(
    func_name: str,
    args: dict,
    all_tools: list,
    conversation_style: str = None,
    tool_event_callback=None
) -> str:
    """
    Execute a single tool call and return the result as a string.

    Args:
        func_name: Name of the tool to execute
        args: Arguments to pass to the tool
        all_tools: List of available tool functions
        conversation_style: Language style for response translation
        tool_event_callback: Optional callback to emit tool execution events.
                             Accepted as either sync (returns None) or async
                             (returns coroutine) — both handled transparently.

    Returns:
        String result from tool execution
    """
    import time
    import asyncio
    import inspect

    start_time = time.time()

    # ── Internal helper: unified sync/async-safe event emitter ───────────────
    async def _emit(event_data: dict) -> None:
        """Call tool_event_callback, awaiting it if it returns a coroutine.
        Never raises — a broken callback must not crash the tool execution."""
        if not tool_event_callback:
            return
        try:
            cb_result = tool_event_callback(event_data)
            if asyncio.iscoroutine(cb_result):
                await cb_result
        except Exception as cb_exc:
            logger.debug("[ToolExecutor] tool_event_callback raised: %s", cb_exc)

    # ── 1. Emit: starting ─────────────────────────────────────────────────────
    await _emit({
        "type": "tool_execution",
        "data": {
            "tool_name": func_name,
            "status": "starting",
            "args": args,
            "timestamp": start_time,
        },
    })

    # ── 2. Resolve native function ────────────────────────────────────────────
    func = next(
        (t for t in all_tools if hasattr(t, "__name__") and t.__name__ == func_name),
        None,
    )

    # ── 3. MCP tool path (name contains "__") ────────────────────────────────
    if not func:
        if "__" in func_name:
            try:
                from ...tools.mcp_service import mcp_service
                result = await mcp_service.call_tool(func_name, args or {})

                if conversation_style:
                    from ._tool_response_translator import translate_tool_response
                    result = translate_tool_response(func_name, result, conversation_style)

                await _emit({
                    "type": "tool_execution",
                    "data": {
                        "tool_name": func_name,
                        "status": "success",
                        "result": str(result)[:200],
                        "duration": time.time() - start_time,
                        "timestamp": time.time(),
                    },
                })
                return str(result)

            except Exception as e:
                await _emit({
                    "type": "tool_execution",
                    "data": {
                        "tool_name": func_name,
                        "status": "failed",
                        "error": str(e),
                        "duration": time.time() - start_time,
                        "timestamp": time.time(),
                    },
                })
                if conversation_style:
                    from ..language_style_enhanced import format_localized_error
                    error_msg = format_localized_error(e, conversation_style)
                    return f"MCP tool '{func_name}': {error_msg}"
                return f"MCP tool '{func_name}' raised an error: {e}"

        # ── 4. Tool not found ─────────────────────────────────────────────────
        await _emit({
            "type": "tool_execution",
            "data": {
                "tool_name": func_name,
                "status": "failed",
                "error": "Tool not available or disabled",
                "duration": time.time() - start_time,
                "timestamp": time.time(),
            },
        })
        if conversation_style == "banglish":
            return f"Tool '{func_name}' available nei ba disable kora ache."
        if conversation_style == "hindilish":
            return f"Tool '{func_name}' available nahi hai ya disable hai."
        return f"Tool '{func_name}' is disabled or not available."

    # ── 5. Native tool execution ──────────────────────────────────────────────
    try:
        if inspect.iscoroutinefunction(func):
            result = await func(**args)
        else:
            result = func(**args)

        if conversation_style:
            from ._tool_response_translator import translate_tool_response
            result = translate_tool_response(func_name, result, conversation_style)

        await _emit({
            "type": "tool_execution",
            "data": {
                "tool_name": func_name,
                "status": "success",
                "result": str(result)[:200],
                "duration": time.time() - start_time,
                "timestamp": time.time(),
            },
        })
        return str(result)

    except Exception as e:
        await _emit({
            "type": "tool_execution",
            "data": {
                "tool_name": func_name,
                "status": "failed",
                "error": str(e),
                "duration": time.time() - start_time,
                "timestamp": time.time(),
            },
        })
        if conversation_style:
            from ..language_style_enhanced import format_localized_error
            error_msg = format_localized_error(e, conversation_style)
            return f"Tool '{func_name}': {error_msg}"
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
