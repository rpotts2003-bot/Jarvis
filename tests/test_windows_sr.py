"""Windows Speech Recognition helper — mocked PowerShell; no Windows required in CI."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from assistant.voice import windows_sr
from assistant.voice.platform_io import make_mic_hear


class _FakeProc:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def test_parse_sr_output_ok():
    raw = "JARVIS_SR_STATUS=ok\nJARVIS_SR_TEXT=what time is it\n"
    parsed = windows_sr._parse_sr_output(raw)
    assert parsed["status"] == "ok"
    assert parsed["text"] == "what time is it"


def test_parse_sr_output_denied():
    raw = "JARVIS_SR_STATUS=denied\nJARVIS_SR_ERROR=access denied\n"
    parsed = windows_sr._parse_sr_output(raw)
    assert parsed["status"] == "denied"
    assert "access" in parsed["error"]


def test_native_sr_supported_linux_default(monkeypatch):
    monkeypatch.delenv("JARVIS_FORCE_WINDOWS_SR", raising=False)
    monkeypatch.delenv("JARVIS_FORCE_GOOGLE_STT", raising=False)
    monkeypatch.setattr(windows_sr.sys, "platform", "linux")
    assert windows_sr.native_sr_supported() is False


def test_native_sr_supported_force_on(monkeypatch, tmp_path):
    script = tmp_path / "windows_listen.ps1"
    script.write_text("# fake\n", encoding="utf-8")
    monkeypatch.setenv("JARVIS_FORCE_WINDOWS_SR", "1")
    monkeypatch.setenv("JARVIS_WINDOWS_LISTEN_PS1", str(script))
    monkeypatch.setenv("JARVIS_POWERSHELL", "/bin/true")
    monkeypatch.delenv("JARVIS_FORCE_GOOGLE_STT", raising=False)
    assert windows_sr.native_sr_supported() is True


def test_native_sr_force_google_disables(monkeypatch, tmp_path):
    script = tmp_path / "windows_listen.ps1"
    script.write_text("# fake\n", encoding="utf-8")
    monkeypatch.setenv("JARVIS_FORCE_WINDOWS_SR", "1")
    monkeypatch.setenv("JARVIS_FORCE_GOOGLE_STT", "1")
    monkeypatch.setenv("JARVIS_WINDOWS_LISTEN_PS1", str(script))
    monkeypatch.setenv("JARVIS_POWERSHELL", "/bin/true")
    assert windows_sr.native_sr_supported() is False


def test_recognize_native_success(monkeypatch, tmp_path):
    script = tmp_path / "windows_listen.ps1"
    script.write_text("# fake\n", encoding="utf-8")
    monkeypatch.setenv("JARVIS_FORCE_WINDOWS_SR", "1")
    monkeypatch.setenv("JARVIS_WINDOWS_LISTEN_PS1", str(script))
    monkeypatch.setenv("JARVIS_POWERSHELL", "/bin/true")

    def runner(cmd, **kwargs):
        assert "-File" in cmd
        assert str(script) in cmd
        assert "-TimeoutSeconds" in cmd
        return _FakeProc(
            stdout="JARVIS_SR_STATUS=ok\nJARVIS_SR_TEXT=hello jarvis\n",
            returncode=0,
        )

    text, err = windows_sr.recognize_native(timeout_s=3.0, runner=runner)
    assert text == "hello jarvis"
    assert err is None


def test_recognize_native_timeout(monkeypatch, tmp_path):
    script = tmp_path / "windows_listen.ps1"
    script.write_text("# fake\n", encoding="utf-8")
    monkeypatch.setenv("JARVIS_FORCE_WINDOWS_SR", "1")
    monkeypatch.setenv("JARVIS_WINDOWS_LISTEN_PS1", str(script))
    monkeypatch.setenv("JARVIS_POWERSHELL", "/bin/true")

    def runner(cmd, **kwargs):
        return _FakeProc(stdout="JARVIS_SR_STATUS=timeout\n", returncode=1)

    text, err = windows_sr.recognize_native(runner=runner)
    assert text is None
    assert err == "timeout"


def test_probe_native_sr(monkeypatch, tmp_path):
    script = tmp_path / "windows_listen.ps1"
    script.write_text("# fake\n", encoding="utf-8")
    monkeypatch.setenv("JARVIS_FORCE_WINDOWS_SR", "1")
    monkeypatch.setenv("JARVIS_WINDOWS_LISTEN_PS1", str(script))
    monkeypatch.setenv("JARVIS_POWERSHELL", "/bin/true")

    def runner(cmd, **kwargs):
        assert "-ProbeOnly" in cmd
        return _FakeProc(
            stdout="JARVIS_SR_STATUS=ok\nJARVIS_SR_PROBE=ready\n",
            returncode=0,
        )

    out = windows_sr.probe_native_sr(runner=runner)
    assert out["status"] == "ok"
    assert out.get("probe") == "ready"


def test_make_windows_sr_hear(monkeypatch, tmp_path):
    script = tmp_path / "windows_listen.ps1"
    script.write_text("# fake\n", encoding="utf-8")
    monkeypatch.setenv("JARVIS_FORCE_WINDOWS_SR", "1")
    monkeypatch.setenv("JARVIS_WINDOWS_LISTEN_PS1", str(script))
    monkeypatch.setenv("JARVIS_POWERSHELL", "/bin/true")
    monkeypatch.delenv("JARVIS_FORCE_GOOGLE_STT", raising=False)

    def runner(cmd, **kwargs):
        return _FakeProc(
            stdout="JARVIS_SR_STATUS=ok\nJARVIS_SR_TEXT=open calculator\n",
            returncode=0,
        )

    hear = windows_sr.make_windows_sr_hear(runner=runner)
    assert hear is not None
    assert hear() == "open calculator"
    assert hear.last_error is None
    assert hear.last_backend == "windows_sr"


def test_make_mic_hear_ptt_uses_native_when_forced(monkeypatch, tmp_path):
    script = tmp_path / "windows_listen.ps1"
    script.write_text("# fake\n", encoding="utf-8")
    monkeypatch.setenv("JARVIS_FORCE_WINDOWS_SR", "1")
    monkeypatch.setenv("JARVIS_WINDOWS_LISTEN_PS1", str(script))
    monkeypatch.setenv("JARVIS_POWERSHELL", "/bin/true")
    monkeypatch.delenv("JARVIS_FORCE_GOOGLE_STT", raising=False)

    def runner(cmd, **kwargs):
        return _FakeProc(
            stdout="JARVIS_SR_STATUS=ok\nJARVIS_SR_TEXT=what time is it\n",
            returncode=0,
        )

    # Patch make_windows_sr_hear's runner by patching run_windows_listen
    monkeypatch.setattr(
        windows_sr,
        "run_windows_listen",
        lambda **kw: {
            "status": "ok",
            "text": "what time is it",
        },
    )
    # Google path would fail without deps — ensure native returns without needing Google
    monkeypatch.setattr(
        "assistant.voice.platform_io._make_google_mic_hear",
        lambda **kw: None,
    )
    hear = make_mic_hear(mode="ptt")
    assert hear is not None
    assert hear() == "what time is it"
    assert getattr(hear, "last_backend", None) == "windows_sr"


def test_make_mic_hear_falls_back_on_unavailable(monkeypatch, tmp_path):
    script = tmp_path / "windows_listen.ps1"
    script.write_text("# fake\n", encoding="utf-8")
    monkeypatch.setenv("JARVIS_FORCE_WINDOWS_SR", "1")
    monkeypatch.setenv("JARVIS_WINDOWS_LISTEN_PS1", str(script))
    monkeypatch.setenv("JARVIS_POWERSHELL", "/bin/true")
    monkeypatch.delenv("JARVIS_FORCE_GOOGLE_STT", raising=False)

    calls = {"google": 0}

    def fake_native_hear_factory(*, on_level=None, timeout_s=8.0, runner=None):
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
            calls["google"] += 1
            hear.last_error = None
            hear.last_peak = 0.2
            return "from google"

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

    hear = make_mic_hear(mode="ptt")
    assert hear is not None
    assert hear() == "from google"
    assert calls["google"] == 1
    assert getattr(hear, "last_backend", None) == "google"


def test_make_mic_hear_no_fallback_on_timeout(monkeypatch):
    calls = {"google": 0}

    def fake_native_hear_factory(*, on_level=None, timeout_s=8.0, runner=None):
        def hear():
            hear.last_error = "timeout"
            hear.last_peak = 0.0
            return None

        hear.last_error = None
        hear.last_peak = 0.0
        hear.on_level = on_level
        return hear

    def fake_google(*, on_level=None, mode="ptt", duration_s=None, wait_speech_s=None):
        def hear():
            calls["google"] += 1
            return "should not run"

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

    hear = make_mic_hear(mode="ptt")
    assert hear is not None
    assert hear() is None
    assert hear.last_error == "timeout"
    assert calls["google"] == 0


def test_wake_mode_uses_native_when_available(monkeypatch):
    """Wake path prefers short Windows SR chunks when native SR is supported."""
    monkeypatch.setattr(windows_sr, "native_sr_supported", lambda: True)

    called = {"native": 0, "timeout_s": None}

    def fake_native(*, on_level=None, timeout_s=8.0, runner=None):
        called["native"] += 1
        called["timeout_s"] = timeout_s

        def hear():
            hear.last_error = None
            hear.last_peak = 0.3
            return "Jarvis what time is it"

        hear.last_error = None
        hear.last_peak = 0.0
        hear.on_level = on_level
        hear.last_backend = "windows_sr"
        return hear

    monkeypatch.setattr(windows_sr, "make_windows_sr_hear", fake_native)
    monkeypatch.setattr(
        "assistant.voice.platform_io._make_google_mic_hear",
        lambda **kw: None,
    )

    hear = make_mic_hear(mode="wake")
    assert hear is not None
    assert called["native"] == 1
    # Wake native timeout should be shorter than Listen (~7s, not 15s)
    assert called["timeout_s"] is not None
    assert 5.0 <= float(called["timeout_s"]) <= 9.0
    assert hear() == "Jarvis what time is it"
    assert getattr(hear, "last_backend", None) == "windows_sr"


def test_run_windows_listen_missing_script(monkeypatch):
    monkeypatch.setattr(windows_sr, "windows_listen_script_path", lambda: None)
    monkeypatch.setattr(windows_sr, "powershell_exe", lambda: "/bin/true")
    out = windows_sr.run_windows_listen()
    assert out["status"] == "unavailable"
