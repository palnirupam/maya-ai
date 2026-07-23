import json

from backend.brain.language_style import (
    BANGLISH,
    ENGLISH,
    HINDILISH,
    LANGUAGE_STYLES,
    detect_conversation_style,
    detect_language_style,
    get_latest_conversation_style,
    latinize_transcript,
    response_style_directive,
    set_latest_conversation_style,
    tts_language_for_style,
)


def test_detector_returns_only_canonical_styles():
    samples = {
        "ekhon eta kore dao": BANGLISH,
        "abhi ye kar do": HINDILISH,
        "please finish this first": ENGLISH,
        "\u0986\u09ae\u09bf \u09ad\u09be\u09b2\u09cb \u0986\u099b\u09bf": BANGLISH,
        "\u092e\u0941\u091d\u0947 \u0905\u092d\u0940 \u0915\u0930\u0928\u093e \u0939\u0948": HINDILISH,
    }

    assert LANGUAGE_STYLES == {BANGLISH, HINDILISH, ENGLISH}
    for text, expected in samples.items():
        assert detect_language_style(text) == expected


def test_short_followups_keep_the_conversation_style():
    history = [
        {"role": "user", "content": "ekhon eta kore dao"},
        {"role": "assistant", "content": "korchi"},
        {"role": "user", "content": "ok"},
        {"role": "assistant", "content": "thik ache"},
        {"role": "user", "content": "continue"},
    ]

    assert detect_conversation_style("continue", history) == BANGLISH
    assert detect_conversation_style("abhi ye karo", history) == HINDILISH


def test_style_directives_lock_one_style_and_use_latin_script():
    for style in LANGUAGE_STYLES:
        directive = response_style_directive(style)
        assert style.upper() in directive
        assert not any("\u0980" <= char <= "\u09ff" for char in directive)
        assert not any("\u0900" <= char <= "\u097f" for char in directive)


def test_stt_native_script_fallback_is_latinized():
    bangla = "\u0986\u09ae\u09bf \u09a4\u09cb\u09ae\u09be\u0995\u09c7 \u09ad\u09be\u09b2\u09cb\u09ac\u09be\u09b8\u09bf"
    hindi = "\u092e\u0941\u091d\u0947 \u092a\u093e\u0928\u0940 \u091a\u093e\u0939\u093f\u090f"

    assert latinize_transcript(bangla) == "ami tomake bhalobasi"
    assert latinize_transcript(hindi) == "mujhe pani chahie"
    assert latinize_transcript("ami need help \u098f\u0996\u09a8") == "ami need help ekhana"


def test_tts_voice_follows_canonical_style():
    assert tts_language_for_style(BANGLISH) == "bn"
    assert tts_language_for_style(HINDILISH) == "hi"
    assert tts_language_for_style(ENGLISH) == "en"


def test_latest_conversation_style_is_shared_across_channels():
    try:
        assert set_latest_conversation_style(BANGLISH) == BANGLISH
        assert get_latest_conversation_style() == BANGLISH
        assert set_latest_conversation_style(HINDILISH) == HINDILISH
        assert get_latest_conversation_style() == HINDILISH
        assert set_latest_conversation_style("unsupported") == HINDILISH
    finally:
        set_latest_conversation_style(ENGLISH)


def test_deterministic_clarification_uses_locked_turn_style():
    from backend.brain.agents.agent_team import _format_clarification

    payload = json.dumps({
        "kind": "contact_pick",
        "query": "Amit",
        "candidates": [
            {"name": "Amit One", "number": "111"},
            {"name": "Amit Two", "number": "222"},
        ],
    })

    banglish = _format_clarification(payload, "ok", BANGLISH)
    hindilish = _format_clarification(payload, "ok", HINDILISH)
    english = _format_clarification(payload, "ok", ENGLISH)

    assert "Kake pathabo" in banglish
    assert "Kise bheju" in hindilish
    assert "Which one should I send" in english
