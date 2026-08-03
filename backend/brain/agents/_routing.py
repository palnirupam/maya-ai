import re
from .intent_parsing import (
    _DIRECT_APP_OPEN_PATTERNS, _DIRECT_APP_CLOSE_PATTERNS, _DIRECT_APP_FOCUS_PATTERNS,
    _DIRECT_APP_BLOCKERS, _OS_BT_RE, _OS_WIFI_RE, _is_followup_modifier,
)
from .tool_router import _SEND_INTENT_RE, _FILE_INTENT_RE
from ._session_state import (
    _LAST_AGENT_BY_SESSION,
    _LAST_DIRECT_APP_BY_SESSION, 
    _LAST_AGENT_MAX_SESSIONS,
    _LAST_DIRECT_APP_NAME,
    _LAST_OS_CONTROL_BY_SESSION,
    _PENDING_SEND_BY_SESSION,
    _PENDING_YOUTUBE_TITLE_BY_SESSION,
    _PENDING_YOUTUBE_MODE_BY_SESSION,
    _SEND_EXECUTING_TOOLS,
    _SEND_FLOW_TOOLS,
    _delivery_fingerprint,
    _remember_last_agent,
    _remember_direct_app,
    _remember_os_control,
    _remember_pending_send,
    _remember_pending_youtube_title,
    _remember_pending_youtube_mode,
    evict_session_state
)

# ── Fast keyword-based router (avoids Gemini API call) ───────────────────────
# Patterns that ALWAYS go to OS_EXECUTOR — no LLM needed
_OS_PATTERNS = re.compile(
    r"(whatsapp|whatapp|whatsap|watsapp|telegram|email|mail|gmail|youtube|chrome|open |start |launch |close |volume|brightness"
    r"|screenshot|screen|type |click|trash|delete|send |send.*message|forward|pathao|pathiye|patha|পাঠা|bhej|vej|chalao|chalu|bondho|kholo|khulo|khul|khol"
    r"|download|install|reminder|schedule|contact|save|recall|forget|skill|mcp|mode.*change"
    r"|professional mode|friendly mode|coding mode|clipboard|process|app "
    r"|select |profile|switch |scroll|press |minimize|maximize|window|browser"
    r"|play |pause|stop |mute|unmute|tab |shortcut|hotkey|drag|resize"
    r"|notif|alarm|timer|khulje|khulte|chalao|band koro|kholo|khulo|dekho|snapshot|camera|camara|photo|picture|selfie|\bdocuments?\b"
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
_CAMERA_LOOK_INTENT_RE = re.compile(
    # Main pattern: outfit/dress/clothes/style + action words
    r"|\b(outfit|dress|clothes|clothing|shirt|tshirt|t-shirt|style|matching|look|appearance|attire|getup|পোশাক|জামা|कपड़े|स्टाইল)\b"
    r".{0,60}\b(how|kemon|kamon|kaisa|kaisi|lagche|lagchhe|lag raha|lag rahi|look|think|opinion|match|check|dekho|dekh|review|bolo|bol|comment|rate|judge|evaluate|analyze|কেমন|দেখো|বলো|রেট|জাজ|এনালাইজ|hai|তো)\b"
    # Question patterns: how/what + outfit/style
    r"|\b(how|what|kemon|kamon|kaisa|kaisi|কেমন|কামন|কৈশা)\b.{0,45}\b(outfit|dress|clothes|clothing|shirt|tshirt|t-shirt|style|look|appearance|পোশাক|জামা|कपड़े|स्টাইल)\b"
    # Direct questions about appearance
    r"|\b(how do i look|how am i looking|kemon lagche|kamon lagche|kaisa lag raha|kaisi lag rahi|আমি কেমন লাগছি|আমার কেমন লাগছে)\b"
    # Action + outfit patterns
    r"|\b(outfit|dress|clothes|clothing|style|look|appearance|পোশাক|জামা).{0,30}\b(check|dekho|dekh|review|bolo|bol|comment|rate|judge|evaluate|analyze|দেখো|বলো|চেক|রিভিউ|রেট)\b"
    # Check/review + outfit patterns  
    r"|\b(check|dekho|dekh|review|comment|rate|judge|evaluate|analyze|tell|say|দেখো|চেক|রিভিউ|বলো|রেট|জাজ).{0,30}\b(outfit|dress|clothes|clothing|style|look|appearance|পোশাক|জামা)\b"
    # Bengali/Hindi specific phrases
    r"|\b(আমার|আমি|আজকে|আজ|today).{0,20}\b(outfit|dress|style|look|পোশাক|জামা).{0,20}\b(কেমন|kemon|kamon|kaisa|lagche|দেখো|বলো)\b"
    # More casual expressions
    r"|\b(ami|আমি|amar|আমার|meri|mere).{0,30}\b(outfit|dress|style|look|পোশাক|জামা|कपड़े|स्टाइल)\b"
    r"|\b(outfit|dress|style|look|পোশাক|জামা|कपड़े|स्टाइल).{0,30}\b(thik|ঠিক|theek|sahi|ভালো|bhalo|good|nice|perfect|matching)\b",
    re.IGNORECASE,
)
# Patterns that ALWAYS go to CHAT (canvas/widget requests — never CODER)
_CODER_PATTERNS = re.compile(
    r"(write.*code|code.*likh|script|python file|run.*\.py|debug|fix.*bug"
    r"|create.*file|edit.*file|read.*file|file.*poro|terminal|powershell"
    r"|project.*create|repo|test.*run)",
    re.IGNORECASE
)

# General camera review for ANY object/item (not just outfit)
_CAMERA_REVIEW_INTENT_RE = re.compile(
    r"\b(এটা|এটি|eta|ita|this|that|এই|ei|ye|yeh)\b.{0,30}\b(দেখো|dekho|dekh|check|review|bolo|kemon|কেমন|kaisa)\b"
    r"|\b(camera|ক্যামেরা).{0,20}\b(দিয়ে|diye|e|te|mein|se).{0,20}\b(দেখো|dekho|check|review)\b"
    r"|\b(review|check|analyze|inspect|examine|dekho|দেখো).{0,20}\b(this|that|এটা|এটি|eta)\b"
    r"|\b(কী|ki|kya|what).{0,10}\b(রে|re|hai|is).{0,10}\b(এটা|এটি|eta|this)\b"
    r"|\b(এই|ei|this|that).{0,20}\b(ফুল|flower|mouse|phone|mobile|product|জিনিস|jinish|item|thing)\b.{0,20}\b(দেখো|dekho|check|review|কেমন|kemon)\b"
    r"|\b(নিয়ে এলাম|নিয়েছি|kine anlam|bought|got).{0,20}\b(দেখো|dekho|check|review|bolo|বলো)\b"
    r"|\b(camera).{0,20}\b(on|open|chalu|চালু).{0,20}\b(koro|করো|do|kar)\b"
    # Additional patterns for missed cases
    r"|(দেখো|dekho).{0,20}(এটা|eta|this)"
    r"|^(এটা|eta).{0,20}(দেখো|কেমন|dekho|kemon)"
    r"|(ফুল|flower|mouse|phone).{0,10}(দেখো|কেমন)"
    r"|(এলাম|anlam).{0,15}(দেখো|dekho)"
    r"|(কী|ki).{0,8}(এটা|eta)",
    re.IGNORECASE | re.UNICODE,
)

_CANVAS_PATTERNS = re.compile(
    r"(tracker|widget|dashboard|kanban|habit.*track|to.?do|todo|planner|calculator"
    r"|ui banao|interactive.*widget|canvas|visualization|chart banao"
    r"|create.*app|build.*app|make.*app|ekta.*tool)",
    re.IGNORECASE
)
# Patterns that signal the user wants a real FILE on disk — these OVERRIDE canvas routing.
_FILE_ON_DISK_PATTERNS = re.compile(
    r"(\b[a-zA-Z]\s*drive\b|\b[a-zA-Z]:\\\\|save.*file|file.*banao|file.*save|disk.*e.*banao"
    r"|html.*file|py.*file|txt.*file|\.html|\.py|\.txt|\.js|\.json|\.csv"
    r"|Desktop.*e|Documents.*e|Downloads.*e)",
    re.IGNORECASE
)

_GREETING_PATTERNS = re.compile(
    r"^(hi|hii|hello|hey|yo|maya|hi maya|hello maya|hey maya|namaste|nomoskar|salaam"
    r"|good morning|good afternoon|good evening|good night|kemon acho|ki khobor|kaise ho)$",
    re.IGNORECASE
)

_FILE_SELECTION_FOLLOWUP_RE = re.compile(
    r"^\s*(?:(?:all|all\s+of\s+them|all\s+three|sob|shob)(?:\s+(?:tai|ta|gulo))?"
    r"|(?:\d+|one|two|three|ek|dui|tin)\s*(?:tai|ta|number)?)\s*[.!]?\s*$",
    re.IGNORECASE,
)

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
    # A local filename is not an app name. Let OS_EXECUTOR use
    # file(action="open") instead of launching Windows Search for it.
    if re.search(r"\.[A-Za-z0-9]{1,8}\b", text) and re.search(
        r"\b(browser|browse|chrome|file)\b", text, re.IGNORECASE
    ):
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


def _format_direct_app_response(
    func_name: str,
    app_name: str,
    result: str,
    style: str = "banglish",
) -> str:
    from ..language_style import BANGLISH, ENGLISH, HINDILISH

    result_lower = result.lower()
    
    # Handle PARTIAL results as partial success, not error
    if result.startswith("PARTIAL"):
        details = result[8:].strip() if len(result) > 8 else result
        if style == ENGLISH or style == "english":
            return f"Partially completed: {details}"
        if style == HINDILISH or style == "hindilish":
            return f"Kuchh ho gaya: {details}"
        return f"Kichuta hoyeche: {details}"
    
    # SUCCESS and OK are full success
    if result.startswith(("SUCCESS", "OK")):
        if func_name == "close_apps_except":
            if style == ENGLISH or style == "english":
                return f"Kept {app_name} open and closed the other safe apps." if app_name else "Closed all safe apps."
            if style == HINDILISH or style == "hindilish":
                return f"{app_name} ko open rakhkar baaki safe apps close kar diye." if app_name else "Saare safe apps close kar diye."
            return f"{app_name} open rekhe baki safe app gulo close kore dilam." if app_name else "Sob safe app close kore dilam."
        if "browser fallback" in result_lower:
            if style == ENGLISH or style == "english":
                return f"I couldn't find the native {app_name} app, so I opened it in the browser."
            if style == HINDILISH or style == "hindilish":
                return f"{app_name} ka native app nahi mila, isliye browser me khol diya."
            return f"{app_name} native app paini, tai browser e open korlam."
        if "windows search" in result_lower:
            if style == ENGLISH or style == "english":
                return f"Tried to open {app_name} through Windows Search."
            if style == HINDILISH or style == "hindilish":
                return f"Windows Search se {app_name} kholne ki koshish ki."
            return f"{app_name} Windows Search diye open korar try korlam."
        if func_name == "close_app":
            return f"Closed {app_name}." if (style == ENGLISH or style == "english") else (f"{app_name} close kar diya." if (style == HINDILISH or style == "hindilish") else f"{app_name} close kore dilam.")
        if func_name == "close_active_window":
            return "Closed the active window." if (style == ENGLISH or style == "english") else ("Active window close kar diya." if (style == HINDILISH or style == "hindilish") else "Active window close kore dilam.")
        if func_name == "focus_app":
            return f"Focused {app_name}." if (style == ENGLISH or style == "english") else (f"{app_name} ko focus kar diya." if (style == HINDILISH or style == "hindilish") else f"{app_name} focus kore dilam.")
        return f"Opened {app_name}." if (style == ENGLISH or style == "english") else (f"{app_name} khol diya." if (style == HINDILISH or style == "hindilish") else f"{app_name} open kore dilam.")
    
    # Only show error message for actual errors (ERR:)
    if result.startswith("ERR"):
        if style == ENGLISH or style == "english":
            return f"I couldn't complete the {app_name} action: {result}"
        if style == HINDILISH or style == "hindilish":
            return f"{app_name} ka action complete nahi hua: {result}"
        return f"{app_name} er kaj korte parlam na: {result}"
    
    # Unknown format - return result as-is
    return result


def _fast_route(
    text: str, last_agent: str | None = None, pending_send: bool = False
) -> list[str] | None:
    """Returns agent list instantly from keywords, or None to fall back to Gemini router."""
    t = text.lower()

    if _CAMERA_LOOK_INTENT_RE.search(text) or _CAMERA_REVIEW_INTENT_RE.search(text):
        return ["OS_EXECUTOR"]

    # Deterministic device controls always outrank canvas/chat heuristics.
    # This protects commands such as "Take photo" even if a previous canvas
    # turn or an overlapping keyword would otherwise bias routing to CHAT.
    from .intent_parsing import _parse_direct_os_action

    if _parse_direct_os_action(text) is not None:
        return ["OS_EXECUTOR"]

    is_canvas = bool(_CANVAS_PATTERNS.search(t))
    is_os = bool(_OS_PATTERNS.search(t))
    is_research = bool(
        _RESEARCH_PATTERNS.search(t) or _TODAY_NEWS_VARIANT_RE.search(t)
    )
    is_coder = bool(_CODER_PATTERNS.search(t))
    # If user mentions a specific drive/path/extension, they want a REAL file —
    # override canvas routing regardless of "banao/game" keywords.
    is_file_on_disk = bool(_FILE_ON_DISK_PATTERNS.search(text))

    # Canvas/widget requests always go to CHAT before file/code routing.
    # BUT if the user explicitly mentions a drive/path, skip canvas and create a real file.
    if is_canvas and not is_file_on_disk:
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

    # A terse selection after a real OS/file listing ("3 tai", "all", "sob")
    # must retain the file-capable agent instead of falling into short CHAT.
    if last_agent == "OS_EXECUTOR" and _FILE_SELECTION_FOLLOWUP_RE.fullmatch(text):
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
