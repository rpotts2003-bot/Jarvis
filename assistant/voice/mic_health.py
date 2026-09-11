"""First-run / Diagnose microphone health check."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from assistant.config import user_data_dir


class MicStatus(str, Enum):
    OK = "ok"
    NO_DEVICE = "no_device"
    PERMISSION = "permission"
    MISSING_DEP = "missing_dep"
    OS_MUTED = "os_muted"


MESSAGES = {
    MicStatus.NO_DEVICE: (
        "No microphone found. Plug one in or set a default in Windows Sound settings."
    ),
    MicStatus.PERMISSION: (
        "Jarvis can't use the mic. Allow microphone access for this app in Windows Privacy settings."
    ),
    MicStatus.MISSING_DEP: (
        "Voice packages missing. Double-click Start Jarvis.bat to install them, then Test mic."
    ),
    MicStatus.OS_MUTED: (
        "Windows has the mic muted or volume at 0. Unmute it in the system tray, then Test mic."
    ),
    MicStatus.OK: "Microphone OK.",
}


@dataclass
class MicProbeResult:
    status: MicStatus
    detail: str = ""

    @property
    def message(self) -> str:
        return MESSAGES[self.status]

    @property
    def ok(self) -> bool:
        return self.status == MicStatus.OK


def prefs_path() -> Path:
    return user_data_dir() / "ui_prefs.json"


def load_prefs() -> dict[str, Any]:
    path = prefs_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_prefs(update: dict[str, Any]) -> None:
    data = load_prefs()
    data.update(update)
    prefs_path().write_text(json.dumps(data, indent=2), encoding="utf-8")


def needs_first_run_probe() -> bool:
    return not bool(load_prefs().get("mic_probed"))


def mark_probed(*, status: str) -> None:
    save_prefs({"mic_probed": True, "mic_last_status": status})


def probe_microphone(*, open_stream: bool = True) -> MicProbeResult:
    """Probe default capture via sounddevice (no PyAudio)."""
    try:
        import sounddevice as sd  # type: ignore
    except Exception as e:
        return MicProbeResult(MicStatus.MISSING_DEP, detail=str(e))

    try:
        devices = sd.query_devices()
    except Exception as e:
        err = str(e).lower()
        if "denied" in err or "permission" in err or "access" in err:
            return MicProbeResult(MicStatus.PERMISSION, detail=str(e))
        return MicProbeResult(MicStatus.NO_DEVICE, detail=str(e))

    inputs = [
        d
        for d in devices
        if isinstance(d, dict) and int(d.get("max_input_channels", 0) or 0) > 0
    ]
    # PortAudio DeviceList may be list-like of dicts
    if not inputs:
        try:
            count = len(devices)  # type: ignore[arg-type]
            for i in range(count):
                d = sd.query_devices(i)
                if int(d.get("max_input_channels", 0) or 0) > 0:
                    inputs.append(d)
        except Exception:
            pass

    if not inputs:
        return MicProbeResult(MicStatus.NO_DEVICE, detail="no input devices")

    if not open_stream:
        return MicProbeResult(MicStatus.OK, detail=f"{len(inputs)} input device(s)")

    try:
        # Short shared-mode capture (~0.2s)
        sd.rec(frames=int(16000 * 0.2), samplerate=16000, channels=1, dtype="float32")
        sd.wait()
        return MicProbeResult(MicStatus.OK, detail=f"{len(inputs)} input device(s)")
    except PermissionError as e:
        return MicProbeResult(MicStatus.PERMISSION, detail=str(e))
    except Exception as e:
        err = str(e).lower()
        if "denied" in err or "permission" in err or "access" in err:
            return MicProbeResult(MicStatus.PERMISSION, detail=str(e))
        if "mute" in err:
            return MicProbeResult(MicStatus.OS_MUTED, detail=str(e))
        return MicProbeResult(MicStatus.NO_DEVICE, detail=str(e))
