"""Shared language-style detection for Maya's text and voice pipelines.

Maya has three canonical conversational styles. All three use Latin script:
Banglish (romanized Bangla), Hindilish (romanized Hindi), and English.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence


BANGLISH = "banglish"
HINDILISH = "hindilish"
ENGLISH = "english"
LANGUAGE_STYLES = frozenset({BANGLISH, HINDILISH, ENGLISH})
_latest_conversation_style = ENGLISH

LANGUAGE_STYLE_POLICY = (
    "MAYA LANGUAGE POLICY (MANDATORY): Maya supports exactly three conversational "
    "response styles, all written with English/Latin letters: "
    "(1) Banglish = Bangla grammar and phrasing in Latin letters, "
    "(2) Hindilish = Hindi grammar and phrasing in Latin letters, and "
    "(3) English = natural English. Detect the user's style and reply in that same "
    "style on every turn, including tool confirmations, errors, safety messages, "
    "and fallback replies. Never output Bengali or Devanagari script in a normal reply. Technical "
    "English terms may stay unchanged inside Banglish or Hindilish. Keep the current "
    "conversation style for short or ambiguous follow-ups unless the user clearly "
    "switches styles or explicitly asks for another one."
)

_BENGALI_SCRIPT_RE = re.compile(r"[\u0980-\u09ff]")
_DEVANAGARI_SCRIPT_RE = re.compile(r"[\u0900-\u097f]")

_WORD_RE = re.compile(r"[a-z]+(?:'[a-z]+)?", re.IGNORECASE)

_BANGLISH_STRONG = frozenset({
    "ami", "amra", "amar", "amader", "amake", "amke",
    "tumi", "tomar", "tomer", "tomake", "apni", "apnar",
    "koro", "korbo", "korchi", "korche", "kore", "korle", "korte",
    "dao", "dibo", "debe", "pathao", "pathiye",
    "ache", "achi", "acho", "nei", "holo", "hoyeche", "hobe", "hocche",
    "jeno", "ektu", "ekhon", "ekhono", "abar", "ajke", "ajker",
    "khobor", "bhalo", "valo", "bujhle", "bhujle", "bujho", "lagbe",
    "kothay", "kemon", "keno", "ebar", "sob", "shob",
})

_HINDILISH_STRONG = frozenset({
    "tum", "tumhe", "tumhara", "tumhari", "mujhe", "mera", "meri",
    "hum", "aap", "aapko", "aapka", "aapki",
    "karo", "karna", "karoge", "karenge", "bhejo", "bhejna", "batao",
    "hai", "hain", "nahi", "kya", "kyun", "kaise", "chahiye",
    "abhi", "samjhe", "samjha", "raha", "rahi", "rahe", "hoga", "hua",
    "accha", "achha", "theek", "matlab", "wala", "wali", "waala", "waali",
})

_BANGLISH_WEAK = frozenset({
    "ta", "er", "te", "eta", "ota", "ekta", "upor", "kaj", "kaaj",
    "bolo", "likho", "ke", "ki",
})

_HINDILISH_WEAK = frozenset({
    "ko", "se", "ka", "ki", "ke", "ye", "woh", "ho", "bolo", "likho",
    "main", "mein", "aur", "par",
})

_ENGLISH_CUES = frozenset({
    "the", "this", "that", "these", "those", "is", "are", "was", "were",
    "can", "could", "would", "should", "please", "explain", "what", "why",
    "where", "when", "how", "with", "from", "into", "for", "and", "you",
    "your", "we", "our", "they", "their", "have", "has", "need", "want",
})

_SHORT_CONTINUATIONS = frozenset({
    "ok", "okay", "yes", "no", "hmm", "fine", "done", "sure", "right",
    "continue", "go", "ahead",
})

_BANGLISH_PHRASES = (
    "kore dao", "ki holo", "ki korcho", "kemon acho", "bujhte perechi",
)
_HINDILISH_PHRASES = (
    "kar do", "kya hua", "kya kar rahe", "kaise ho", "samajh gaye",
)

_BENGALI_VOWELS = {
    "\u0985": "o", "\u0986": "a", "\u0987": "i", "\u0988": "i",
    "\u0989": "u", "\u098a": "u", "\u098b": "ri", "\u098f": "e",
    "\u0990": "oi", "\u0993": "o", "\u0994": "ou",
}
_BENGALI_CONSONANTS = {
    "\u0995": "k", "\u0996": "kh", "\u0997": "g", "\u0998": "gh", "\u0999": "ng",
    "\u099a": "ch", "\u099b": "chh", "\u099c": "j", "\u099d": "jh", "\u099e": "n",
    "\u099f": "t", "\u09a0": "th", "\u09a1": "d", "\u09a2": "dh", "\u09a3": "n",
    "\u09a4": "t", "\u09a5": "th", "\u09a6": "d", "\u09a7": "dh", "\u09a8": "n",
    "\u09aa": "p", "\u09ab": "ph", "\u09ac": "b", "\u09ad": "bh", "\u09ae": "m",
    "\u09af": "j", "\u09b0": "r", "\u09b2": "l", "\u09b6": "sh", "\u09b7": "sh",
    "\u09b8": "s", "\u09b9": "h", "\u09dc": "r", "\u09dd": "rh", "\u09df": "y",
    "\u09ce": "t",
}
_BENGALI_SIGNS = {
    "\u09be": "a", "\u09bf": "i", "\u09c0": "i", "\u09c1": "u", "\u09c2": "u",
    "\u09c3": "ri", "\u09c7": "e", "\u09c8": "oi", "\u09cb": "o", "\u09cc": "ou",
}
_BENGALI_MARKS = {"\u0981": "n", "\u0982": "ng", "\u0983": "h"}

_DEVANAGARI_VOWELS = {
    "\u0905": "a", "\u0906": "aa", "\u0907": "i", "\u0908": "i",
    "\u0909": "u", "\u090a": "u", "\u090b": "ri", "\u090f": "e",
    "\u0910": "ai", "\u0913": "o", "\u0914": "au",
}
_DEVANAGARI_CONSONANTS = {
    "\u0915": "k", "\u0916": "kh", "\u0917": "g", "\u0918": "gh", "\u0919": "ng",
    "\u091a": "ch", "\u091b": "chh", "\u091c": "j", "\u091d": "jh", "\u091e": "n",
    "\u091f": "t", "\u0920": "th", "\u0921": "d", "\u0922": "dh", "\u0923": "n",
    "\u0924": "t", "\u0925": "th", "\u0926": "d", "\u0927": "dh", "\u0928": "n",
    "\u092a": "p", "\u092b": "ph", "\u092c": "b", "\u092d": "bh", "\u092e": "m",
    "\u092f": "y", "\u0930": "r", "\u0932": "l", "\u0935": "v", "\u0936": "sh",
    "\u0937": "sh", "\u0938": "s", "\u0939": "h", "\u0958": "q", "\u0959": "kh",
    "\u095a": "gh", "\u095b": "z", "\u095c": "r", "\u095d": "rh", "\u095e": "f",
}
_DEVANAGARI_SIGNS = {
    "\u093e": "a", "\u093f": "i", "\u0940": "i", "\u0941": "u", "\u0942": "u",
    "\u0943": "ri", "\u0947": "e", "\u0948": "ai", "\u094b": "o", "\u094c": "au",
}
_DEVANAGARI_MARKS = {"\u0901": "n", "\u0902": "n", "\u0903": "h", "\u093d": "'"}


def _normalize_fallback(fallback: str | None) -> str | None:
    return fallback if fallback in LANGUAGE_STYLES else None


def detect_language_style(text: str, fallback: str | None = None) -> str:
    """Classify text as Banglish, Hindilish, or English.

    ``fallback`` is used for genuinely short/ambiguous follow-ups so a message
    such as "ok" or "status ki" does not unexpectedly switch the conversation.
    Bengali and Devanagari input map to their Latin-script product styles.
    """
    fallback = _normalize_fallback(fallback)
    raw = text or ""

    if any("\u0980" <= char <= "\u09ff" for char in raw):
        return BANGLISH
    if any("\u0900" <= char <= "\u097f" for char in raw):
        return HINDILISH

    tokens = [token.lower() for token in _WORD_RE.findall(raw)]
    if not tokens:
        return fallback or ENGLISH

    joined = " ".join(tokens)
    banglish_score = 3 * sum(token in _BANGLISH_STRONG for token in tokens)
    banglish_score += sum(token in _BANGLISH_WEAK for token in tokens)
    banglish_score += 3 * sum(phrase in joined for phrase in _BANGLISH_PHRASES)

    hindilish_score = 3 * sum(token in _HINDILISH_STRONG for token in tokens)
    hindilish_score += sum(token in _HINDILISH_WEAK for token in tokens)
    hindilish_score += 3 * sum(phrase in joined for phrase in _HINDILISH_PHRASES)

    english_score = sum(token in _ENGLISH_CUES for token in tokens)

    if banglish_score >= 3 and banglish_score > hindilish_score:
        return BANGLISH
    if hindilish_score >= 3 and hindilish_score > banglish_score:
        return HINDILISH

    if banglish_score == hindilish_score and banglish_score >= 3:
        return fallback if fallback in {BANGLISH, HINDILISH} else BANGLISH

    if english_score >= 2 or len(tokens) > 5:
        return ENGLISH

    if fallback and (
        len(tokens) <= 4
        or all(token in _SHORT_CONTINUATIONS for token in tokens)
    ):
        return fallback

    # "ki" is a common short Banglish status/question marker. Hindilish has
    # stronger unambiguous markers such as "kya", "hai", "karo", and "bhejo".
    if banglish_score > hindilish_score or "ki" in tokens:
        return BANGLISH
    if hindilish_score > banglish_score:
        return HINDILISH
    return ENGLISH


def detect_conversation_style(
    text: str,
    context_history: Sequence[Mapping[str, object]] | None = None,
) -> str:
    """Detect a turn's style while preserving short follow-up continuity."""
    current = (text or "").strip()

    user_messages = [
        str(message.get("content", "")).strip()
        for message in (context_history or [])
        if message.get("role") == "user" and str(message.get("content", "")).strip()
    ]
    # The orchestrator appends the current user turn before invoking the agent
    # team. Remove only that final duplicate, while retaining an older identical
    # message as genuine conversation history.
    if user_messages and user_messages[-1] == current:
        user_messages.pop()

    previous_style: str | None = None
    for content in user_messages:
        previous_style = detect_language_style(content, fallback=previous_style)

    return detect_language_style(text, fallback=previous_style)


def response_style_directive(style: str) -> str:
    """Return a strict per-turn prompt directive for one canonical style."""
    if style == BANGLISH:
        return (
            "RESPONSE STYLE (MANDATORY): BANGLISH. Use natural Bangla grammar and "
            "phrasing written only with English/Latin letters. Do not use Bengali "
            "script. Technical English words are fine."
        )
    if style == HINDILISH:
        return (
            "RESPONSE STYLE (MANDATORY): HINDILISH. Use natural Hindi grammar and "
            "phrasing written only with English/Latin letters. Do not use Devanagari "
            "script. Technical English words are fine."
        )
    return (
        "RESPONSE STYLE (MANDATORY): ENGLISH. Reply in natural English; do not "
        "switch to Banglish or Hindilish."
    )


def response_matches_style(text: str, style: str) -> bool:
    """Conservative production check for the three canonical output styles."""
    raw = text or ""
    if _BENGALI_SCRIPT_RE.search(raw) or _DEVANAGARI_SCRIPT_RE.search(raw):
        return False
    if style not in LANGUAGE_STYLES:
        return False
    if not raw.strip():
        return True

    detected = detect_language_style(raw)
    if style == ENGLISH:
        return detected == ENGLISH
    if detected == style:
        return True

    tokens = [token.lower() for token in _WORD_RE.findall(raw)]
    if style == BANGLISH:
        return any(token in _BANGLISH_STRONG for token in tokens)
    return any(token in _HINDILISH_STRONG for token in tokens)


def style_repair_prompt(text: str, style: str) -> str:
    """Prompt used only when a final model reply violates the locked turn style."""
    return (
        f"Rewrite the message below in the mandatory {style.upper()} response style. "
        "Preserve every fact, number, path, error, and conclusion. Do not add or remove information. "
        "Use only English/Latin letters and output only the rewritten message.\n\n"
        f"Message:\n{text}"
    )


def set_latest_conversation_style(style: str) -> str:
    """Remember the personal assistant user's latest conversational style."""
    global _latest_conversation_style
    if style in LANGUAGE_STYLES:
        _latest_conversation_style = style
    return _latest_conversation_style


def get_latest_conversation_style() -> str:
    """Return the latest style observed across Maya's active user channels."""
    return _latest_conversation_style


def tts_language_for_style(style: str) -> str:
    """Map conversational style to the closest configured Indian TTS voice."""
    return {BANGLISH: "bn", HINDILISH: "hi", ENGLISH: "en"}.get(style, "en")


def _romanize_indic(
    text: str,
    vowels: Mapping[str, str],
    consonants: Mapping[str, str],
    vowel_signs: Mapping[str, str],
    marks: Mapping[str, str],
    virama: str,
    nukta: str,
) -> str:
    """Romanize one Indic abugida while leaving all other text untouched."""
    output: list[str] = []
    has_inherent_vowel = False

    for char in text:
        if char in consonants:
            output.extend((consonants[char], "a"))
            has_inherent_vowel = True
        elif char in vowel_signs:
            if has_inherent_vowel and output and output[-1] == "a":
                output.pop()
            output.append(vowel_signs[char])
            has_inherent_vowel = False
        elif char == virama:
            if has_inherent_vowel and output and output[-1] == "a":
                output.pop()
            has_inherent_vowel = False
        elif char == nukta:
            continue
        elif char in vowels:
            output.append(vowels[char])
            has_inherent_vowel = False
        elif char in marks:
            output.append(marks[char])
            has_inherent_vowel = False
        elif "\u09e6" <= char <= "\u09ef":
            output.append(str(ord(char) - ord("\u09e6")))
            has_inherent_vowel = False
        elif "\u0966" <= char <= "\u096f":
            output.append(str(ord(char) - ord("\u0966")))
            has_inherent_vowel = False
        elif char in {"\u0964", "\u0965"}:
            output.append(".")
            has_inherent_vowel = False
        else:
            output.append(char)
            has_inherent_vowel = False

    return "".join(output)


def latinize_transcript(text: str) -> str:
    """Return STT text with Bangla/Hindi script converted to Latin letters.

    Gemini is instructed to produce Latin text directly. This deterministic
    fallback also handles native-script output from Whisper or a provider that
    ignores that instruction, while preserving existing Latin/English spans.
    """
    result = _romanize_indic(
        text or "",
        _BENGALI_VOWELS,
        _BENGALI_CONSONANTS,
        _BENGALI_SIGNS,
        _BENGALI_MARKS,
        "\u09cd",
        "\u09bc",
    )
    result = _romanize_indic(
        result,
        _DEVANAGARI_VOWELS,
        _DEVANAGARI_CONSONANTS,
        _DEVANAGARI_SIGNS,
        _DEVANAGARI_MARKS,
        "\u094d",
        "\u093c",
    )
    # Drop any rare script code point not covered by the phonetic tables. STT
    # must never leak native-script characters into the Latin-only pipeline.
    result = re.sub(r"[\u0900-\u097f\u0980-\u09ff]", "", result)
    return re.sub(r"[ \t]+", " ", result).strip()
