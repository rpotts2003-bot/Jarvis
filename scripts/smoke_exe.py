"""Post-build smoke against dist/Jarvis.exe (Ideas acceptance)."""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", type=Path, default=Path("dist") / "Jarvis.exe")
    ap.add_argument(
        "--StrictMic",
        action="store_true",
        help="Also fail on no_device/permission/os_muted (not just missing_dep).",
    )
    args = ap.parse_args()
    exe = args.exe

    if not exe.exists():
        print(f"Smoke stopped: {exe} not found.")
        return 1

    report = exe.parent / "jarvis_diagnose.txt"
    if report.exists():
        try:
            report.unlink()
        except Exception:
            pass

    # Windowed exe: diagnose writes jarvis_diagnose.txt beside itself
    try:
        proc = subprocess.run(
            [str(exe), "diagnose"],
            cwd=str(exe.parent),
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        print("Smoke stopped: frozen diagnose timed out.")
        return 1
    except OSError as e:
        print(f"Smoke stopped: could not launch exe ({e}).")
        return 1

    # Brief wait for file flush
    for _ in range(20):
        if report.exists():
            break
        time.sleep(0.1)

    if not report.exists():
        # Fallback: module diagnose (dev machines without frozen report)
        print("NOTE: no jarvis_diagnose.txt from exe — falling back to python -m assistant diagnose")
        r = subprocess.run([sys.executable, "-m", "assistant", "diagnose"])
        if r.returncode == 2:
            print("Smoke stopped: voice deps missing (missing_dep).")
        return r.returncode

    body = report.read_text(encoding="utf-8", errors="replace")
    print(body)

    mic = ""
    for line in body.splitlines():
        if line.startswith("mic:"):
            mic = line.split(":", 1)[1].strip()
        if line.startswith("tts: fail"):
            print("Smoke stopped: frozen TTS path crashed.")
            return 1
        if line.startswith("crash:"):
            print("Smoke stopped: frozen diagnose crashed.")
            return 1

    if mic == "missing_dep":
        print("Smoke stopped: frozen voice stack missing_dep (rebuild after requirements-voice.txt).")
        return 2

    if args.StrictMic and mic and mic != "ok":
        print(f"Smoke stopped: StrictMic and mic={mic}.")
        return 3

    if mic and mic != "ok":
        print(f"Smoke soft-warn: mic={mic} (allowed unless -StrictMic).")

    print("SMOKE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
