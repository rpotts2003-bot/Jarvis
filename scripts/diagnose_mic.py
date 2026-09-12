#!/usr/bin/env python3
"""Mic reliability diagnose: list default device, native SR probe, capture peak/rms.

Usage (from repo root):
  python scripts/diagnose_mic.py
  python -m assistant diagnose

Writes jarvis_mic_diagnose.txt under ~/.jarvis (and cwd). No cloud keys needed.
Does not prove Windows privacy settings on a Linux CI box — check peak on the PC.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from assistant.config import user_data_dir
    from assistant.envload import load_env
    from assistant.voice.mic_health import mark_probed, probe_microphone
    from assistant.voice.platform_io import _PTT_DURATION_S, _WAKE_DURATION_S, _vad_enabled
    from assistant.voice import windows_sr

    load_env()
    lines: list[str] = []
    lines.append(f"jarvis mic diagnose @ {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"platform: {sys.platform}")
    lines.append(f"ptt_duration_s: {_PTT_DURATION_S}")
    lines.append(f"wake_duration_s: {_WAKE_DURATION_S}")
    lines.append(f"vad_enabled: {_vad_enabled()}")

    # Native Windows Speech Recognition availability
    lines.append("--- native_windows_sr ---")
    script = windows_sr.windows_listen_script_path()
    lines.append(f"script: {script}")
    lines.append(f"powershell: {windows_sr.powershell_exe()}")
    lines.append(f"native_sr_supported: {windows_sr.native_sr_supported()}")
    try:
        probe = windows_sr.probe_native_sr()
        lines.append(f"native_probe_status: {probe.get('status')}")
        if probe.get("error"):
            lines.append(f"native_probe_error: {probe.get('error')}")
        if probe.get("probe"):
            lines.append(f"native_probe: {probe.get('probe')}")
        # Optional short Recognize test when probe is ready (Windows only)
        if (
            probe.get("status") == windows_sr.STATUS_OK
            and sys.platform.startswith("win")
        ):
            lines.append("native_recognize_test: speaking window ~3s — say something…")
            text, err = windows_sr.recognize_native(timeout_s=3.0)
            if text:
                lines.append(f"native_recognize_text: {text!r}")
            else:
                lines.append(f"native_recognize_error: {err}")
    except Exception as e:  # noqa: BLE001
        lines.append(f"native_probe_exception: {e}")

    # Device list (best-effort)
    try:
        import sounddevice as sd  # type: ignore

        lines.append("--- devices ---")
        try:
            default = sd.query_devices(kind="input")
            lines.append(f"default_input: {default}")
        except Exception as e:
            lines.append(f"default_input_error: {e}")
        try:
            for i, d in enumerate(sd.query_devices()):
                if int(d.get("max_input_channels", 0) or 0) > 0:
                    lines.append(
                        f"  [{i}] {d.get('name')} ch={d.get('max_input_channels')} "
                        f"rate={d.get('default_samplerate')}"
                    )
        except Exception as e:
            lines.append(f"list_error: {e}")
    except Exception as e:
        lines.append(f"sounddevice_missing: {e}")

    lines.append("--- probe ---")
    result = probe_microphone(open_stream=True)
    mark_probed(status=result.status.value)
    lines.append(f"status: {result.status.value}")
    lines.append(f"ok: {result.ok}")
    lines.append(f"message: {result.message}")
    lines.append(f"detail: {result.detail}")
    lines.append(f"peak: {result.peak:.6f}")
    lines.append(f"rms: {result.rms:.6f}")
    lines.append(f"device_name: {result.device_name}")
    lines.append(f"sample_rate: {result.sample_rate}")

    if result.ok and result.peak < 1e-5:
        lines.append(
            "HINT: stream opened but peak flat — unmute Windows mic, set default "
            "device, allow mic privacy for Python/Jarvis, then speak during Listen."
        )
    elif not result.ok:
        lines.append("HINT: fix status above, then re-run. Typing in the HUD still works.")
    if sys.platform.startswith("win"):
        lines.append(
            "HINT: Listen uses Windows Speech Recognition when available "
            "(Privacy → Microphone must allow apps/Python)."
        )

    code = 0 if result.ok else 3
    if result.status.value == "missing_dep":
        code = 2
    lines.append(f"exit: {code}")
    text = "\n".join(lines) + "\n"

    targets = [
        user_data_dir() / "jarvis_mic_diagnose.txt",
        Path.cwd() / "jarvis_mic_diagnose.txt",
    ]
    for path in targets:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            print(f"wrote: {path}")
        except Exception as e:
            print(f"write_fail: {path} ({e})")
    print(text, end="")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
