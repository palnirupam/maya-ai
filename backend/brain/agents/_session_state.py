import json
from collections import OrderedDict

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
