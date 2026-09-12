"""Input device auto-pick + flat-mic tip (mocked sounddevice)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from assistant.voice import platform_io
from assistant.voice import windows_sr


def test_flat_mic_tip_wording():
    assert "Mic level flat (0%)" in platform_io.FLAT_MIC_TIP
    assert "Discord/Zoom" in platform_io.FLAT_MIC_TIP
    assert "Privacy" in platform_io.FLAT_MIC_TIP


def test_recognize_native_no_fake_vu(monkeypatch, tmp_path):
    script = tmp_path / "windows_listen.ps1"
    script.write_text("# fake\n", encoding="utf-8")
    monkeypatch.setenv("JARVIS_FORCE_WINDOWS_SR", "1")
    monkeypatch.setenv("JARVIS_WINDOWS_LISTEN_PS1", str(script))
    monkeypatch.setenv("JARVIS_POWERSHELL", "/bin/true")

    levels: list[float] = []

    def runner(cmd, **kwargs):
        return SimpleNamespace(
            stdout="JARVIS_SR_STATUS=ok\nJARVIS_SR_TEXT=hello\n",
            stderr="",
            returncode=0,
        )

    text, err, conf = windows_sr.recognize_native(
        timeout_s=3.0,
        on_level=levels.append,
        runner=runner,
    )
    assert text == "hello"
    assert err is None
    assert conf is None
    assert levels == []  # no fake 0.35/0.55


def test_resolve_input_device_prefers_live(monkeypatch, tmp_path):
    prefs = tmp_path / "ui_prefs.json"
    prefs.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(platform_io, "_prefs_path", lambda: prefs)

    devices = {
        0: {"name": "Dead Mic", "max_input_channels": 1, "default_samplerate": 16000},
        1: {"name": "Live Mic", "max_input_channels": 1, "default_samplerate": 16000},
    }

    class FakeSD:
        class default:
            device = (0, None)

        @staticmethod
        def query_devices(device=None, kind=None):
            if kind == "input":
                return devices[0]
            if device is None:
                return [devices[0], devices[1]]
            return devices[int(device)]

        @staticmethod
        def wait():
            return None

        @staticmethod
        def rec(frames, samplerate=16000, channels=1, dtype="float32", device=None):
            import numpy as np

            idx = 0 if device is None else int(device)
            peak = 0.00001 if idx == 0 else 0.05
            return (np.ones((frames, 1), dtype=np.float32) * peak)

    monkeypatch.setitem(__import__("sys").modules, "sounddevice", FakeSD)
    # Also need numpy - already present in venv usually
    chosen = platform_io.resolve_input_device(force_rescan=True)
    assert chosen == 1
    data = prefs.read_text(encoding="utf-8")
    assert "Live Mic" in data


def test_fallback_sets_status_note(monkeypatch):
    def fake_native_hear_factory(*, on_level=None, timeout_s=8.0, mode="listen", runner=None):
        def hear():
            hear.last_error = "unavailable"
            hear.last_peak = 0.0
            return None

        hear.last_error = None
        hear.last_peak = 0.0
        hear.on_level = on_level
        return hear

    def fake_google(*, on_level=None, mode="ptt", duration_s=None, wait_speech_s=None):
        def hear():
            hear.last_error = "mic"
            hear.last_peak = 0.0
            return None

        hear.last_error = None
        hear.last_peak = 0.0
        hear.on_level = on_level
        hear.mode = mode
        return hear

    monkeypatch.setattr(windows_sr, "make_windows_sr_hear", fake_native_hear_factory)
    monkeypatch.setattr(windows_sr, "native_sr_supported", lambda: True)
    monkeypatch.setattr(
        "assistant.voice.platform_io._make_google_mic_hear", fake_google
    )

    hear = platform_io.make_mic_hear(mode="ptt")
    assert hear is not None
    assert hear() is None
    assert "Windows SR unavailable" in (hear.status_note or "")
    assert hear.last_error == "mic"
    assert hear.last_peak < 0.01


def test_listen_and_wake_timeouts():
    assert platform_io._PTT_DURATION_S >= 14.0
    assert platform_io._NATIVE_LISTEN_TIMEOUT_S >= 14.0
    assert platform_io._WAKE_NATIVE_TIMEOUT_S >= 6.0
    assert windows_sr._NATIVE_TIMEOUT_S >= 14.0
