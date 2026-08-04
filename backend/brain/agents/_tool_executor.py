import logging
from ..providers.gemini_adapter import gemini_adapter

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


async def _run_tool(func_name: str, args: dict, all_tools: list, conversation_style: str = None) -> str:
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
                # Translate MCP tool response
                if conversation_style:
                    from ._tool_response_translator import translate_tool_response
                    result = translate_tool_response(func_name, result, conversation_style)
                return str(result)
            except Exception as e:
                # Translate error message
                if conversation_style:
                    from ..language_style_enhanced import format_localized_error
                    error_msg = format_localized_error(e, conversation_style)
                    return f"MCP tool '{func_name}': {error_msg}"
                return f"MCP tool '{func_name}' raised an error: {e}"
        
        # Translate "tool not available" message
        if conversation_style:
            from ..language_style_enhanced import get_localized_message
            msg = get_localized_message("error", conversation_style)
            if conversation_style == "banglish":
                return f"Tool '{func_name}' available nei ba disable kora ache."
            elif conversation_style == "hindilish":
                return f"Tool '{func_name}' available nahi hai ya disable hai."
            
        return f"Tool '{func_name}' is disabled or not available."
        
    try:
        import inspect
        if inspect.iscoroutinefunction(func):
            result = await func(**args)
        else:
            result = func(**args)
            
        # Translate tool response to match conversation style
        if conversation_style:
            from ._tool_response_translator import translate_tool_response
            result = translate_tool_response(func_name, result, conversation_style)
            
        return str(result)
    except Exception as e:
        # Translate error message
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
