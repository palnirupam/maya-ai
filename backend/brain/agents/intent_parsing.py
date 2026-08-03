"""
Intent parsing (pure, dependency-free)
======================================
Deterministic, regex-only helpers that decide whether a request is a simple
laptop control (open app, set volume, brightness, mute, read clipboard) that can
be executed WITHOUT an LLM call. Kept in a leaf module (imports only ``re``) so
it stays hermetically unit-testable — importing it never pulls in the heavy
agent/provider/tool chain.

agent_team.py imports these and dispatches them before the LLM loop.
"""
from __future__ import annotations

import re


# ── App control gates (open / close / focus) ─────────────────────────────────
_DIRECT_APP_OPEN_PATTERNS = re.compile(
    r"\b(open|launch|start|chalao|chalu|kholo|khulo|khul|khol|khulte)\b",
    re.IGNORECASE,
)
_DIRECT_APP_CLOSE_PATTERNS = re.compile(
    r"\b(close|bondho|band)\b",
    re.IGNORECASE,
)
_DIRECT_APP_FOCUS_PATTERNS = re.compile(
    r"\b(focus|switch)\b",
    re.IGNORECASE,
)
# If any of these appear, the text is NOT a bare app/control command (it's a
# message, a question, or a complaint) — fall back to the LLM.
_DIRECT_APP_BLOCKERS = re.compile(
    r"\b(send|message|msg|pathao|call|reply|read|poro|delete|trash|revoke"
    r"|problem|somossa|sommosha|issue|fail|failed|parche|perche|parchi|keno|why"
    r"|hocche\s+na|hochhe\s+na|hoche\s+na|hoyni|hoye\s+ni|not\s+opening)\b",
    re.IGNORECASE,
)


# A request such as "yt te cinema chaliye dao" is materially different from
# background audio: the user expects visible YouTube playback. Keep this
# detector here so it can take the same deterministic path as simple desktop
# commands.
_YOUTUBE_SITE_RE = re.compile(r"\b(?:youtube|yt)\b", re.IGNORECASE)
_YOUTUBE_PLAY_RE = re.compile(
    r"\b(?:play|chalao|chaliye|chalai|dekhao|dekhte|watch|cinema|movie|film|video)\b",
    re.IGNORECASE,
)
_YOUTUBE_QUERY_NOISE = {
    "youtube", "yt", "open", "launch", "start", "kholo", "khulo",
    "khul", "khol", "chalu", "kore", "koro", "kor", "dao", "de",
    "nao", "please", "pls", "play", "chalao", "chaliye", "chalai",
    "dekhao", "dekhte", "watch", "maya", "te",
}
_YOUTUBE_GENERIC_VIDEO_QUERIES = {"cinema", "movie", "film", "video"}


def parse_foreground_youtube_play_intent(text: str) -> str | None:
    """Return a YouTube search query for a visible-playback request.

    The presence of YouTube and a playback/video term means the user expects a
    visible browser window, not VLC's headless audio player.
    """
    raw = (text or "").strip()
    if re.search(r"\bbackground\b", raw, re.IGNORECASE):
        return None
    if not (
        _YOUTUBE_SITE_RE.search(raw)
        and _YOUTUBE_PLAY_RE.search(raw)
    ):
        return None

    words = re.findall(r"[A-Za-z0-9]+", raw)
    query = " ".join(word for word in words if word.lower() not in _YOUTUBE_QUERY_NOISE)
    return query or None


def is_generic_youtube_video_query(query: str | None) -> bool:
    """True when a YouTube playback request still needs a movie/video title."""
    words = re.findall(r"[A-Za-z0-9]+", query or "")
    return bool(words) and all(word.lower() in _YOUTUBE_GENERIC_VIDEO_QUERIES for word in words)


# ── YouTube playback mode (visible screen vs background audio) ───────────────
# "yt e video dekhbo" → the user will WATCH: visible browser playback.
# "background e chalao" / "shunbo" → audio only: VLC background player.
# Neither word present ("yt e arijit er gaan chalao") → ambiguous: Maya must
# ASK before playing so audio never pops a browser window (and vice versa).
_YOUTUBE_WATCH_MODE_RE = re.compile(
    r"\b(?:dekh\w*|watch\w*|video|cinema|movie|film|screen|samne|foreground)\b"
    r"|দেখ|ভিডিও|সিনেমা|স্ক্রিন|देख|स्क्रीन",
    re.IGNORECASE,
)
_YOUTUBE_LISTEN_MODE_RE = re.compile(
    r"\b(?:background|audio|shun\w*|shon\w*|sun(?:bo|te|b|i)\w*"
    r"|sunn?[au]\w*|sunlo|suno|sunenge)\b"
    r"|শুন|শোন|ব্যাকগ্রাউন্ড|सुन",
    re.IGNORECASE,
)


def parse_youtube_mode_answer(text: str) -> str | None:
    """'foreground' | 'background' if the text states HOW to play, else None."""
    raw = text or ""
    if _YOUTUBE_LISTEN_MODE_RE.search(raw):
        return "background"
    if _YOUTUBE_WATCH_MODE_RE.search(raw):
        return "foreground"
    return None


# ── Follow-up modifier ("50% koro", "aro barao") ─────────────────────────────
# A bare value ("50", "50%") optionally followed by a Bengali/Banglish verb...
_BARE_VALUE_MODIFIER = re.compile(
    r"^\s*\d{1,3}\s*%?"
    r"(?:\s*(?:koro|kore|kor|kore dao|kore nao|de|dao|nao|set|করো|কর|দাও|নাও))?"
    r"\s*$",
    re.IGNORECASE,
)
# ...or a small set of adjustment words that continue a prior action.
_ADJUST_WORD_MODIFIER = re.compile(
    r"\b(aro|aru|আরো|আরও|beshi|বেশি|kom|কম|barao|baralo|বাড়াও|বাড়া|komao|কমাও|komiye"
    r"|half|full|max|maximum|min|minimum|low|high|dim|medium|mid|lowest|highest|puro"
    r"|mute|unmute|louder|softer|upore|niche)\b",
    re.IGNORECASE,
)


def _is_followup_modifier(text: str) -> bool:
    """True if `text` looks like a short adjustment continuing a prior action."""
    words = text.split()
    if not words or len(words) > 4:
        return False
    t = text.lower()
    return bool(_BARE_VALUE_MODIFIER.match(t) or _ADJUST_WORD_MODIFIER.search(t))


# ── WhatsApp explicit UI-automation trigger ─────────────────────────────────
# When the user says something like "WhatsApp open kore X find kore hi likho send
# koro", we want the OS_EXECUTOR to use the desktop UI (whatsapp_ui_send_message)
# instead of the background Baileys service.  This regex only detects the intent;
# LLM/function-calling extracts the actual contact name and message.
_WHATSAPP_UI_RE = re.compile(
    r"\b(whatsapp|whatapp|whatsap|watsapp|whats app)\b"
    r".{0,40}?"
    r"\b(open|kholo|khulo|khol|khule|khulte|launch|start|chalao)\b"
    r".{0,60}?"
    r"\b(find|search|khuj|khoj|khoje|khuji|dekho|naam)\b"
    r".{0,250}?"
    r"\b(send|pathao|pathiye|patha|likh|likho|lekh|bhej|vej|bhejo|vejo)\b",
    re.IGNORECASE | re.DOTALL,
)


def is_whatsapp_ui_intent(text: str) -> bool:
    """True if the text requests the full WhatsApp Desktop open-find-type-send flow."""
    return bool(_WHATSAPP_UI_RE.search(text or ""))


# ── Deterministic OS controls (zero-LLM) ─────────────────────────────────────
# Simple laptop controls (volume / brightness / mute / clipboard-read) are pure
# regex → tool, no LLM call at all — instant, free, and more reliable. Screenshot
# is intentionally NOT here: take_verified_screenshot returns base64 for the
# vision pipeline, so it must stay on the LLM path.
_OS_VOLUME_RE = re.compile(r"\b(volume|sound|audio|awaz|awaj)\b|আওয়াজ|ভলিউম|শব্দ", re.IGNORECASE)
_OS_BRIGHTNESS_RE = re.compile(r"\b(brightness|bright)\b|উজ্জ্বলতা", re.IGNORECASE)
_OS_MUTE_RE = re.compile(
    r"\b(mute|unmute)\b|\b(sound|volume|awaz)\s*(off|on|bondho|band|bnd|chalu)\b",
    re.IGNORECASE,
)
_OS_CLIPBOARD_RE = re.compile(r"\bclipboard\b|ক্লিপবোর্ড", re.IGNORECASE)
_OS_CAMERA_PHOTO_RE = re.compile(
    r"\b(?:(?:take|click|capture|tolo|tul|tule)\s+(?:a\s+)?(?:photo|picture|selfie)"
    r"|(?:photo|picture|selfie)\s+(?:take|click|capture|tolo|tul|tule|dao))\b",
    re.IGNORECASE,
)
# Bluetooth / WiFi — common misspellings included ("blootooth" seen in live log).
_OS_BT_RE = re.compile(
    r"\b(bluetooth|blutooth|blootooth|bluetuth|blueth?ooth?|bt)\b|ব্লুটুথ|ব্লু টুথ",
    re.IGNORECASE,
)
_OS_WIFI_RE = re.compile(r"\b(wi-?fi|wifi|wlan)\b|ওয়াইফাই|ওয়াই-ফাই|ওয়াই ফাই", re.IGNORECASE)
# Lock (\b excludes "unlock" — no boundary between 'n' and 'l') and battery status.
# Lock and battery are safe for a zero-LLM bypass. Power commands are parsed
# deterministically too, but agent_team still sends them through its explicit
# approval gate before executing the unified pc tool.
_OS_LOCK_RE = re.compile(r"\block\b|লক", re.IGNORECASE)
_OS_BATTERY_RE = re.compile(r"\bbattery\b|ব্যাটারি|charge koto|koto charge", re.IGNORECASE)
_OS_POWER_PATTERNS = (
    ("shutdown", re.compile(
        r"\b(shut\s*down|power\s*off)\b|শাটডাউন"
        r"|(?:পিসি|ল্যাপটপ|কম্পিউটার|সিস্টেম)\s*(?:টা|টি)?\s*বন্ধ\s*(?:করো|করে দাও)",
        re.IGNORECASE,
    )),
    ("restart", re.compile(r"\b(restart|reboot)\b|রিস্টার্ট", re.IGNORECASE)),
    ("hibernate", re.compile(r"\bhibernate\b|হাইবারনেট", re.IGNORECASE)),
    ("sleep", re.compile(
        r"\b(?:pc|laptop|computer|system)\s*(?:ke\s*)?sleep\b|\bsleep\s*mode\b|স্লিপ\s*মোড",
        re.IGNORECASE,
    )),
)
_OS_ON_RE = re.compile(r"\b(on|chalu|cholu|enable|start)\b|অন|চালু", re.IGNORECASE)
_OS_OFF_RE = re.compile(r"\b(off|bondho|bondo|band|bnd|disable)\b|বন্ধ|অফ", re.IGNORECASE)
# Questions about BT/WiFi state ("bluetooth on ache?", "wifi ki on?") must NOT
# toggle anything — leave them to the LLM (which has pc/bt_status).
_OS_TOGGLE_QUESTION_RE = re.compile(r"\?|\b(ki|ache|acche|kina|status)\b|কি|আছে", re.IGNORECASE)
_OS_CLIPBOARD_READ_HINT = re.compile(
    r"\b(read|show|what|content|poro|por|dekhao|dekh|ache|ki)\b|কি|পড়", re.IGNORECASE
)
_OS_LEVEL_RE = re.compile(r"\b(\d{1,3})\b")
_OS_UP_RE = re.compile(r"\b(up|barao|baralo|bariye|increase|beshi|upore)\b|বাড়া", re.IGNORECASE)
_OS_DOWN_RE = re.compile(r"\b(down|komao|kom|komiye|decrease|niche)\b|কমা", re.IGNORECASE)

# Named levels: "volume full", "brightness low", "sound half" → absolute %.
_OS_NAMED_LEVEL = {
    "full": 100, "maximum": 100, "max": 100, "highest": 100, "puro": 100,
    "high": 80,
    "half": 50, "medium": 50, "mid": 50, "majhamajhi": 50,
    "low": 25, "dim": 25, "kom": 25,
    "minimum": 10, "min": 10, "lowest": 10,
}
_OS_NAMED_LEVEL_RE = re.compile(
    r"\b(full|maximum|max|highest|puro|high|half|medium|mid|majhamajhi"
    r"|low|dim|minimum|min|lowest)\b",
    re.IGNORECASE,
)


def _extract_os_level(text: str) -> int | None:
    """First 0-100 integer in the text, or None."""
    m = _OS_LEVEL_RE.search(text)
    if not m:
        return None
    val = int(m.group(1))
    return val if 0 <= val <= 100 else None


def _resolve_os_level(text: str) -> int | None:
    """An explicit number (0-100) OR a named level ("full", "low", "half")."""
    lvl = _extract_os_level(text)
    if lvl is not None:
        return lvl
    m = _OS_NAMED_LEVEL_RE.search(text)
    if m:
        return _OS_NAMED_LEVEL[m.group(1).lower()]
    return None


def _parse_direct_os_action(text: str, last_control: str | None = None):
    """Deterministic path for simple laptop controls.

    Returns (func_name, kwargs, control_type, display_msg) or None. Anything
    ambiguous/complex returns None so the LLM agent handles it.
    """
    t = text.lower().strip()
    if _DIRECT_APP_BLOCKERS.search(t):   # "why/problem/fail/send/read..." → not a control
        return None
    if len(t.split()) > 6:
        return None

    # Bluetooth / WiFi toggle — checked first (more specific than mute/volume).
    # Dispatched through the unified `pc` router; only an explicit on/off intent
    # qualifies, status questions ("bluetooth on ache?") stay on the LLM path.
    bt = _OS_BT_RE.search(t)
    wifi = _OS_WIFI_RE.search(t)
    if bt or wifi:
        if _OS_TOGGLE_QUESTION_RE.search(t):
            return None
        if _OS_OFF_RE.search(t):
            state = "off"
        elif _OS_ON_RE.search(t):
            state = "on"
        else:
            return None
        action = "bt_toggle" if bt else "wifi_toggle"
        label = "Bluetooth" if bt else "WiFi"
        return ("pc", {"action": action, "state": state}, None, f"{label} {state} kore dilam.")

    # Mute / unmute (toggle) — check before volume so "volume off" maps here.
    if _OS_MUTE_RE.search(t):
        return ("perform_shortcut", {"action": "mute"}, None, "Sound mute/unmute kore dilam.")

    # Lock — single reversible keystroke, safe to bypass the LLM.
    if _OS_LOCK_RE.search(t):
        return ("perform_shortcut", {"action": "lock"}, None, "PC lock kore dilam.")

    # Verify a new Camera Roll image before reporting success.
    if _OS_CAMERA_PHOTO_RE.search(t):
        return ("pc", {"action": "camera_photo"}, None, None)

    # Power controls are deterministic so the model cannot invent a capability
    # refusal. The caller recognizes these pc actions as dangerous and pauses
    # for approval before invoking the tool.
    for action, pattern in _OS_POWER_PATTERNS:
        if pattern.search(t):
            messages = {
                "shutdown": "PC 5 second-er moddhe shutdown hobe.",
                "restart": "PC 5 second-er moddhe restart hobe.",
                "sleep": "PC sleep-e jacche.",
                "hibernate": "PC hibernate-e jacche.",
            }
            return ("pc", {"action": action}, None, messages[action])

    # Battery status — read-only, safe to bypass the LLM even when phrased as a question.
    if _OS_BATTERY_RE.search(t):
        return ("pc", {"action": "battery"}, None, None)

    # Brightness — number ("60"), named ("low"/"full"), or relative ("barao").
    if _OS_BRIGHTNESS_RE.search(t):
        lvl = _resolve_os_level(t)
        if lvl is not None:
            return ("control_brightness", {"direction": str(lvl)}, "brightness", f"Brightness {lvl}% kore dilam.")
        if _OS_UP_RE.search(t):
            return ("control_brightness", {"direction": "up"}, "brightness", "Brightness bariye dilam.")
        if _OS_DOWN_RE.search(t):
            return ("control_brightness", {"direction": "down"}, "brightness", "Brightness kamiye dilam.")
        return None

    # Volume — number or named ("full"/"half"/"low"). "volume barao" (no target) → LLM.
    if _OS_VOLUME_RE.search(t):
        lvl = _resolve_os_level(t)
        if lvl is not None:
            return ("change_volume", {"level": lvl}, "volume", f"Volume {lvl}% kore dilam.")
        return None

    # Clipboard read (safe, no args)
    if _OS_CLIPBOARD_RE.search(t) and _OS_CLIPBOARD_READ_HINT.search(t):
        return ("read_clipboard", {}, None, None)

    # Bare follow-up ("50% koro", "full koro", "low") continuing the last control.
    if last_control in ("volume", "brightness") and _is_followup_modifier(t):
        lvl = _resolve_os_level(t)
        if lvl is not None:
            if last_control == "volume":
                return ("change_volume", {"level": lvl}, "volume", f"Volume {lvl}% kore dilam.")
            return ("control_brightness", {"direction": str(lvl)}, "brightness", f"Brightness {lvl}% kore dilam.")
    return None


def _format_direct_os_response(
    func_name: str,
    result: str,
    display_msg: str | None,
    style: str = "banglish",
    kwargs: dict | None = None,
) -> str:
    """User-facing reply for a deterministic OS control."""
    from ..language_style import BANGLISH, ENGLISH, HINDILISH

    r = str(result)
    if r.upper().startswith(("ERR", "BLOCKED", "FAIL")):
        if style == ENGLISH:
            return f"I couldn't complete that action: {r}"
        if style == HINDILISH:
            return f"Yeh action complete nahi hua: {r}"
        return f"Kaj ta korte parlam na: {r}"

    if func_name == "read_clipboard":
        snippet = r if len(r) <= 500 else r[:500] + " ..."
        if style == ENGLISH:
            return f"Clipboard content:\n{snippet}" if snippet.strip() else "The clipboard is empty."
        if style == HINDILISH:
            return f"Clipboard me yeh hai:\n{snippet}" if snippet.strip() else "Clipboard abhi khaali hai."
        return f"Clipboard e ache:\n{snippet}" if snippet.strip() else "Clipboard ekhon khali."

    action = str((kwargs or {}).get("action") or "")
    if func_name == "pc" and action == "camera_photo":
        if r.upper().startswith("PARTIAL:"):
            details = r[8:].strip() if len(r) > 8 else r
            if style == ENGLISH:
                return f"Photo taken but couldn't verify save location: {details}"
            if style == HINDILISH:
                return f"Photo le li lekin save location confirm nahi kar payi: {details}"
            return f"Photo tulechi kintu file location confirm korte parini: {details}"
        if r.upper().startswith(("SUCCESS:", "OK:")):
            # Extract path from "SUCCESS: Camera photo saved: /path/to/file.jpg" or "OK: /path"
            if ":" in r and len(r.split(":", 2)) >= 3:
                path = r.split(":", 2)[-1].strip()
            else:
                path = r.split(":", 1)[-1].strip()
            if style == ENGLISH:
                return f"Took the photo and saved it here: {path}"
            if style == HINDILISH:
                return f"Photo le li aur yahan save kar diya: {path}"
            return f"Photo tule ekhane save kore dilam: {path}"

    if func_name == "pc" and display_msg is None:
        if style == ENGLISH:
            return f"Current status:\n{r}"
        if style == HINDILISH:
            return f"Current status yeh hai:\n{r}"
        return f"Current status:\n{r}"

    if style == BANGLISH:
        return display_msg or "Hoye geche."
    if func_name == "change_volume":
        level = (kwargs or {}).get("level")
        return f"Volume set to {level}%." if style == ENGLISH else f"Volume {level}% kar diya."
    if func_name == "control_brightness":
        value = (kwargs or {}).get("direction")
        return f"Brightness set to {value}." if style == ENGLISH else f"Brightness {value} kar di."
    if action:
        return f"Completed {action}." if style == ENGLISH else f"{action} complete kar diya."
    return "Done." if style == ENGLISH else "Ho gaya."
