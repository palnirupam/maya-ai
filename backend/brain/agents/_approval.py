from dataclasses import dataclass

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
