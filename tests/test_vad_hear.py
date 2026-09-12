"""Pure VAD helpers — no mic hardware required."""

from assistant.voice.platform_io import (
    level_from_rms,
    pcm_rms,
    should_end_on_silence,
    speech_detected,
)
from assistant.voice.tts_style import short_edge_voice_name


def test_pcm_rms_silence_and_tone():
    assert pcm_rms([0.0, 0.0, 0.0]) == 0.0
    assert pcm_rms([0.5, -0.5, 0.5, -0.5]) > 0.4


def test_speech_detected_threshold():
    assert not speech_detected(0.001, threshold=0.018)
    assert speech_detected(0.05, threshold=0.018)


def test_silence_end():
    assert not should_end_on_silence(0.5, needed_s=0.85)
    assert should_end_on_silence(0.85, needed_s=0.85)
    assert should_end_on_silence(1.0, needed_s=0.85)


def test_level_from_rms_clamped():
    assert level_from_rms(0.0) == 0.0
    assert 0.0 < level_from_rms(0.05) <= 1.0
    assert level_from_rms(1.0) == 1.0


def test_short_edge_voice_name():
    assert short_edge_voice_name("en-GB-RyanNeural") == "Ryan"
    assert short_edge_voice_name("en-GB-ThomasNeural") == "Thomas"
    assert short_edge_voice_name("") == "Edge"
