import json
import logging
from datetime import datetime, timezone, timedelta
from .agent_defs import compose_os_prompt
from ..language_style import BANGLISH, ENGLISH, HINDILISH, LANGUAGE_STYLES, detect_language_style, response_style_directive

logger = logging.getLogger(__name__)

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

_SYSTEM_COPY = {
    "music_stopped": {
        BANGLISH: "Gaan bondho kore dilam.",
        HINDILISH: "Gaana band kar diya.",
        ENGLISH: "Music stopped.",
    },
    "music_stop_failed": {
        BANGLISH: "Gaan bondho korte parlam na: {detail}",
        HINDILISH: "Gaana band nahi hua: {detail}",
        ENGLISH: "Could not stop music: {detail}",
    },
    "power_denied": {
        BANGLISH: "Approval na paoyay power command execute kora hoyni.",
        HINDILISH: "Anumati nahi mili, power command execute nahi kiya.",
        ENGLISH: "Power command was not executed — user did not approve.",
    },
    "canvas_updated": {
        BANGLISH: "✅ Canvas panel-e check koro, update kore diyechi!",
        HINDILISH: "✅ Canvas panel me check karo, update kar diya hai!",
        ENGLISH: "✅ Please check the Canvas panel, I've updated it!",
    },
    "generic_success": {
        BANGLISH: "✅ Kaj hoye geche: {clean_msg}",
        HINDILISH: "✅ Kaam ho gaya: {clean_msg}",
        ENGLISH: "✅ Done: {clean_msg}",
    },
    "app_close_denied": {
        BANGLISH: "Approval na paoway baki app gulo close kora hoyni.",
        HINDILISH: "Approval nahi mila, isliye baaki apps close nahi kiye.",
        ENGLISH: "The other apps were not closed because approval was not granted.",
    },
    "unknown_app_denied": {
        BANGLISH: "'{app_name}' app ta chinte parlam na, tai kholini.",
        HINDILISH: "'{app_name}' app ko pehchan nahi payi, isliye nahi khola.",
        ENGLISH: "I didn't recognize the '{app_name}' app, so I didn't open it.",
    },
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
