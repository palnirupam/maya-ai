# agent_team.py — backward-compatible re-export shim
# This file previously contained all agent logic (~2200 lines).
# It has been split into focused modules. All public symbols are re-exported here
# so existing imports (from .agent_team import execute_workflow) keep working.

from ._approval import (
    FailureRecord, MAX_TOOL_OUTPUT_CHARS, DANGER_TOOLS,
    _DANGER_PC_ACTIONS, _DANGER_SHORTCUT_ACTIONS, _DANGER_FILE_ACTIONS,
    _ACTION_ALIASES, _canonical_action, _tool_call_requires_approval,
)
from ._session_state import (
    _LAST_AGENT_MAX_SESSIONS, _LAST_AGENT_BY_SESSION, _LAST_DIRECT_APP_BY_SESSION,
    _LAST_DIRECT_APP_NAME, _LAST_OS_CONTROL_BY_SESSION,
    _PENDING_SEND_BY_SESSION, _PENDING_YOUTUBE_TITLE_BY_SESSION,
    _PENDING_YOUTUBE_MODE_BY_SESSION, _SEND_EXECUTING_TOOLS, _SEND_FLOW_TOOLS,
    _delivery_fingerprint, _remember_last_agent, _remember_direct_app,
    _remember_os_control, _remember_pending_send, _remember_pending_youtube_title,
    _remember_pending_youtube_mode, evict_session_state,
)
from ._routing import (
    _OS_PATTERNS, _RESEARCH_PATTERNS, _STRONG_RESEARCH_PATTERNS, _TODAY_NEWS_VARIANT_RE,
    _OS_STATUS_RE, _CODER_PATTERNS, _CANVAS_PATTERNS, _FILE_ON_DISK_PATTERNS,
    _GREETING_PATTERNS, _FILE_SELECTION_FOLLOWUP_RE, _ANCHOR_MAX_WORDS,
    _BULK_APP_WORDS_RE, _APP_EXCEPT_BEFORE_RE, _APP_EXCEPT_AFTER_RE,
    _carries_tool_signal, _tool_router_query, _last_app_from_history,
    _parse_bulk_app_close, _parse_direct_app_action, _fast_route,
    _previous_user_messages, _router_context_prefix,
)
from ._context_builder import (
    _IST, _CLARIFY_PICK, _CLARIFY_NOT_FOUND, _NOT_FOUND_DETAIL,
    _YT_TITLE_REQUEST, _YT_MODE_REQUEST, _YT_FG_SUCCESS, _YT_FG_PARTIAL,
    _YT_FG_FAILED, _YT_BG_SUCCESS, _YT_BG_FAILED, _SYSTEM_COPY,
    _detect_user_lang, _style_msg, _format_clarification, _is_pref_true,
    _render_time_block, _build_agent_context,
)
from ._tool_executor import (
    _declared_tool_names, _merge_mcp_tool_schemas,
    _summarize_completed_actions, _run_tool, _log_fast_path,
)
from ._workflow import execute_workflow

__all__ = ["execute_workflow", "evict_session_state"]
