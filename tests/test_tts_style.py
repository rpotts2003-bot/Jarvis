from assistant.voice.tts_style import pick_best_voice_id, score_windows_voice


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


def test_hint_override():
    voices = [
        ("george", "Microsoft George Desktop - English (Great Britain)"),
        ("ryan", "Microsoft Ryan Online (Natural) - English (United Kingdom)"),
    ]
    assert pick_best_voice_id(voices, prefer_hint="Ryan") == "ryan"
