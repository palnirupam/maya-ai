"""Unit tests for the STT noise/hallucination guards in transcriber.py.

These cover the pure filter helpers only; they intentionally exercise the
functions that decide whether a transcript is real speech vs. noise Whisper
(or Gemini) invented from silence/ambient sound. Importing the module loads the
Whisper singleton once, which is acceptable for these deterministic checks.
"""
from backend.voice.input.transcriber import (
    _collapse_repeats,
    _is_probable_hallucination,
)


def test_collapse_repeats_reduces_back_to_back_phrase():
    assert _collapse_repeats(["aap", "kaise", "hain"] * 4) == ["aap", "kaise", "hain"]
    assert _collapse_repeats(["you", "you", "you"]) == ["you"]
    # A non-repeating command is left untouched.
    assert _collapse_repeats(["open", "notepad"]) == ["open", "notepad"]
    # A partial/uneven repeat is not a clean multiple → left as-is.
    assert _collapse_repeats(["a", "b", "a"]) == ["a", "b", "a"]


def test_repeated_listed_phrase_is_hallucination():
    # The exact log case: "aap kaise hain" x4 from background noise.
    assert _is_probable_hallucination(
        "Aap kaise hain? Aap kaise hain? Aap kaise hain? Aap kaise hain?"
    )


def test_novel_repeated_garbage_is_hallucination():
    # Not in the block-list, but low unique-word ratio gives it away.
    assert _is_probable_hallucination("blah blah blah blah blah")
    # <= 0.4 unique ratio (2 unique / 5) — dominated by one repeated token.
    assert _is_probable_hallucination("thank thank thank thank you")


def test_real_commands_are_not_hallucinations():
    assert not _is_probable_hallucination("notepad kholo")
    assert not _is_probable_hallucination("Maya please open whatsapp for me")
    assert not _is_probable_hallucination("ekhon ekta email likhe dao")


def test_empty_and_punctuation_only_are_hallucinations():
    assert _is_probable_hallucination("")
    assert _is_probable_hallucination("...")
    assert _is_probable_hallucination("।।")
