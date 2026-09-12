from assistant.voice.adapters import MockTTS
from assistant.voice.platform_io import gui_uses_noop_orch_tts
from assistant.voice.tts_style import (
    is_female_voice_label,
    is_male_voice_label,
    pick_best_voice_id,
    score_windows_voice,
)


def test_uk_male_beats_us_female():
    assert score_windows_voice("Microsoft George Desktop - English (Great Britain)") > score_windows_voice(
        "Microsoft Zira Desktop - English (United States)"
    )


def test_pick_george():
    voices = [
        ("zira", "Microsoft Zira Desktop - English (United States)"),
        ("george", "Microsoft George Desktop - English (Great Britain)"),
        ("hazel", "Microsoft Hazel Desktop - English (Great Britain)"),
    ]
    assert pick_best_voice_id(voices) == "george"


def test_never_pick_zira_hazel_when_david_present():
    """Zira+Hazel+David must never land on female voices when David exists."""
    voices = [
        ("zira", "Microsoft Zira Desktop - English (United States)"),
        ("hazel", "Microsoft Hazel Desktop - English (Great Britain)"),
        ("david", "Microsoft David Desktop - English (United States)"),
    ]
    pick = pick_best_voice_id(voices)
    assert pick == "david"
    assert pick not in {"zira", "hazel"}


def test_never_pick_female_when_george_present():
    voices = [
        ("zira", "Microsoft Zira Desktop - English (United States)"),
        ("hazel", "Microsoft Hazel Desktop - English (Great Britain)"),
        ("george", "Microsoft George Desktop - English (Great Britain)"),
        ("david", "Microsoft David Desktop - English (United States)"),
    ]
    assert pick_best_voice_id(voices) == "george"


def test_female_only_may_pick_least_bad():
    """Female-only inventory: may return least-bad (often UK Hazel over US Zira)."""
    voices = [
        ("zira", "Microsoft Zira Desktop - English (United States)"),
        ("hazel", "Microsoft Hazel Desktop - English (Great Britain)"),
    ]
    pick = pick_best_voice_id(voices)
    assert pick in {"zira", "hazel"}
    # Hazel scores higher (UK) — least-bad documented behavior
    assert pick == "hazel"


def test_hint_override():
    voices = [
        ("george", "Microsoft George Desktop - English (Great Britain)"),
        ("ryan", "Microsoft Ryan Online (Natural) - English (United Kingdom)"),
    ]
    assert pick_best_voice_id(voices, prefer_hint="Ryan") == "ryan"


def test_gender_helpers():
    assert is_female_voice_label("Microsoft Zira Desktop")
    assert is_female_voice_label("Microsoft Hazel Desktop - English (Great Britain)")
    assert is_male_voice_label("Microsoft George Desktop - English (Great Britain)")
    assert is_male_voice_label("Microsoft David Desktop")
    assert not is_male_voice_label("Microsoft Zira Desktop")


def test_gui_uses_noop_orch_tts_helper():
    assert gui_uses_noop_orch_tts(MockTTS(), lambda _t: None) is True
    assert gui_uses_noop_orch_tts(MockTTS(), None) is False
