"""Windows Speech Recognition via System.Speech (PowerShell helper).

Primary Listen path on Windows: uses the OS default microphone through
SpeechRecognitionEngine + DictationGrammar. Falls back to sounddevice+Google
when this helper is unavailable (non-Windows / missing PowerShell / SR load fail).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Literal

# Status strings mirrored from scripts/windows_listen.ps1
STATUS_OK = "ok"
STATUS_TIMEOUT = "timeout"
STATUS_EMPTY = "empty"
STATUS_DENIED = "denied"
STATUS_MIC = "mic"
STATUS_UNAVAILABLE = "unavailable"
STATUS_ERROR = "error"

SrMode = Literal["listen", "wake"]

_NATIVE_TIMEOUT_S = 15.0
_LINE_STATUS = re.compile(r"^JARVIS_SR_STATUS=(.*)$")
_LINE_TEXT = re.compile(r"^JARVIS_SR_TEXT=(.*)$")
_LINE_ERROR = re.compile(r"^JARVIS_SR_ERROR=(.*)$")
_LINE_PROBE = re.compile(r"^JARVIS_SR_PROBE=(.*)$")
_LINE_CONF = re.compile(r"^JARVIS_SR_CONF=(.*)$")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def windows_listen_script_path() -> Path | None:
    """Locate scripts/windows_listen.ps1 (dev tree, frozen, or env override)."""
    env = (os.environ.get("JARVIS_WINDOWS_LISTEN_PS1") or "").strip()
    if env:
        p = Path(env)
        if p.is_file():
            return p

    candidates: list[Path] = [
        _repo_root() / "scripts" / "windows_listen.ps1",
        Path.cwd() / "scripts" / "windows_listen.ps1",
    ]
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.insert(0, exe_dir / "scripts" / "windows_listen.ps1")
        candidates.insert(0, exe_dir / "windows_listen.ps1")
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.insert(0, Path(meipass) / "scripts" / "windows_listen.ps1")

    for path in candidates:
        try:
            if path.is_file():
                return path
        except Exception:
            continue
    return None


def powershell_exe() -> str | None:
    """Best-effort powershell.exe on PATH (Windows)."""
    if os.environ.get("JARVIS_POWERSHELL"):
        return os.environ["JARVIS_POWERSHELL"]
    which = shutil.which("powershell") or shutil.which("powershell.exe")
    if which:
        return which
    # Common install when PATH is thin
    for candidate in (
        r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
        r"C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe",
    ):
        if Path(candidate).is_file():
            return candidate
    return None


def native_sr_supported() -> bool:
    """True when we should attempt Windows native SR (platform + script + shell)."""
    force_off = os.environ.get("JARVIS_FORCE_GOOGLE_STT", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if force_off:
        return False
    force_on = os.environ.get("JARVIS_FORCE_WINDOWS_SR", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not (sys.platform.startswith("win") or force_on):
        return False
    if windows_listen_script_path() is None:
        return False
    if powershell_exe() is None and not force_on:
        return False
    return True


def _parse_sr_output(stdout: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (stdout or "").splitlines():
        line = line.strip()
        m = _LINE_STATUS.match(line)
        if m:
            out["status"] = m.group(1).strip()
            continue
        m = _LINE_TEXT.match(line)
        if m:
            out["text"] = m.group(1)
            continue
        m = _LINE_ERROR.match(line)
        if m:
            out["error"] = m.group(1)
            continue
        m = _LINE_PROBE.match(line)
        if m:
            out["probe"] = m.group(1).strip()
            continue
        m = _LINE_CONF.match(line)
        if m:
            out["confidence"] = m.group(1).strip()
            continue
    return out


def run_windows_listen(
    *,
    timeout_s: float = _NATIVE_TIMEOUT_S,
    probe_only: bool = False,
    mode: SrMode = "listen",
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
) -> dict[str, str]:
    """Invoke windows_listen.ps1. Returns parsed status dict.

    Keys: status, text?, error?, probe?, confidence?
    status may be: ok|timeout|empty|denied|mic|unavailable|error
    """
    script = windows_listen_script_path()
    ps = powershell_exe()
    if script is None or ps is None:
        return {
            "status": STATUS_UNAVAILABLE,
            "error": "powershell or windows_listen.ps1 missing",
        }

    use_mode: SrMode = "wake" if mode == "wake" else "listen"
    cmd = [
        ps,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-TimeoutSeconds",
        str(float(timeout_s)),
        "-Mode",
        use_mode,
    ]
    if probe_only:
        cmd.append("-ProbeOnly")

    run = runner or subprocess.run
    try:
        # Extra wall time beyond Recognize timeout for process startup
        wall = max(15.0, float(timeout_s) + 12.0)
        if probe_only:
            wall = 20.0
        proc = run(
            cmd,
            capture_output=True,
            text=True,
            timeout=wall,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as e:
        return {"status": STATUS_UNAVAILABLE, "error": str(e)}
    except subprocess.TimeoutExpired:
        return {"status": STATUS_TIMEOUT, "error": "powershell timed out"}
    except Exception as e:  # noqa: BLE001
        return {"status": STATUS_ERROR, "error": str(e)}

    parsed = _parse_sr_output((proc.stdout or "") + "\n" + (proc.stderr or ""))
    if "status" not in parsed:
        if proc.returncode == 0 and probe_only:
            parsed["status"] = STATUS_OK
        elif proc.returncode == 0:
            parsed["status"] = STATUS_EMPTY
        else:
            parsed["status"] = STATUS_UNAVAILABLE
            parsed.setdefault(
                "error",
                (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()[:200],
            )
    return parsed


def probe_native_sr(
    *,
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
) -> dict[str, str]:
    """Lightweight availability check (no Recognize listen window)."""
    if not native_sr_supported() and not os.environ.get("JARVIS_FORCE_WINDOWS_SR"):
        return {
            "status": STATUS_UNAVAILABLE,
            "error": "not Windows or helper missing",
        }
    return run_windows_listen(probe_only=True, runner=runner)


def recognize_native(
    *,
    timeout_s: float = _NATIVE_TIMEOUT_S,
    mode: SrMode = "listen",
    on_level: Callable[[float], None] | None = None,
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
) -> tuple[str | None, str | None, float | None]:
    """Recognize one utterance. Returns (text, error_kind, confidence).

    error_kind is None on success; otherwise timeout|empty|denied|mic|unavailable|error.
    confidence is 0..1 when the helper emitted JARVIS_SR_CONF=, else None.

    Does not fake VU levels — native SR has no sample peak; GUI shows
    "(Windows mic)" instead of "level 0%".
    """
    # Intentionally do not call on_level with placeholder peaks (0.35/0.55).
    # Fake levels made captions show bogus % and hid flat-mic failures.
    _ = on_level  # reserved for future real meter if SR exposes audio
    parsed = run_windows_listen(
        timeout_s=timeout_s, probe_only=False, mode=mode, runner=runner
    )
    status = (parsed.get("status") or STATUS_ERROR).strip().lower()
    text = (parsed.get("text") or "").strip()
    conf: float | None = None
    raw_conf = (parsed.get("confidence") or "").strip()
    if raw_conf:
        try:
            conf = float(raw_conf)
        except ValueError:
            conf = None
    if status == STATUS_OK and text:
        return text, None, conf
    if status == STATUS_OK and not text:
        return None, STATUS_EMPTY, conf
    # Map unknown statuses to error
    if status not in {
        STATUS_TIMEOUT,
        STATUS_EMPTY,
        STATUS_DENIED,
        STATUS_MIC,
        STATUS_UNAVAILABLE,
        STATUS_ERROR,
    }:
        status = STATUS_ERROR
    return None, status, conf


def make_windows_sr_hear(
    *,
    on_level: Callable[[float], None] | None = None,
    timeout_s: float = _NATIVE_TIMEOUT_S,
    mode: SrMode = "listen",
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
) -> Callable[[], str | None] | None:
    """Callable hear() using native Windows SR, or None if unsupported."""
    if not native_sr_supported():
        return None

    def hear() -> str | None:
        hear.last_error = None  # type: ignore[attr-defined]
        hear.last_peak = 0.0  # type: ignore[attr-defined]
        hear.last_confidence = None  # type: ignore[attr-defined]
        hear.last_backend = "windows_sr"  # type: ignore[attr-defined]
        level_cb = hear.on_level  # type: ignore[attr-defined]
        text, err, conf = recognize_native(
            timeout_s=float(hear.timeout_s),  # type: ignore[attr-defined]
            mode=hear.sr_mode,  # type: ignore[attr-defined]
            on_level=level_cb,
            runner=runner,
        )
        hear.last_confidence = conf  # type: ignore[attr-defined]
        if text:
            hear.last_peak = 0.4  # type: ignore[attr-defined]
            return text
        hear.last_error = err  # type: ignore[attr-defined]
        return None

    hear.last_error = None  # type: ignore[attr-defined]
    hear.last_peak = 0.0  # type: ignore[attr-defined]
    hear.last_confidence = None  # type: ignore[attr-defined]
    hear.last_backend = "windows_sr"  # type: ignore[attr-defined]
    hear.on_level = on_level  # type: ignore[attr-defined]
    hear.mode = "ptt" if mode == "listen" else "wake"  # type: ignore[attr-defined]
    hear.sr_mode = mode  # type: ignore[attr-defined]
    hear.timeout_s = timeout_s  # type: ignore[attr-defined]
    return hear
