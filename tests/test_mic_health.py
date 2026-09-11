from assistant.voice.mic_health import MESSAGES, MicStatus, probe_microphone


def test_message_wording():
    assert "No microphone found" in MESSAGES[MicStatus.NO_DEVICE]
    assert "Privacy settings" in MESSAGES[MicStatus.PERMISSION]
    assert "setup.ps1" in MESSAGES[MicStatus.MISSING_DEP]
    assert "system tray" in MESSAGES[MicStatus.OS_MUTED]
    assert MESSAGES[MicStatus.OK] == "Microphone OK."


def test_probe_never_crashes():
    r = probe_microphone()
    assert r.status in {
        MicStatus.OK,
        MicStatus.MISSING_DEP,
        MicStatus.NO_DEVICE,
        MicStatus.PERMISSION,
        MicStatus.OS_MUTED,
    }
    assert r.message
