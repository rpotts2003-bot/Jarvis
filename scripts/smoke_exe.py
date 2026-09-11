"""Post-build smoke: run diagnose against frozen exe or python -m assistant."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--exe",
        type=Path,
        default=Path("dist") / "Jarvis.exe",
        help="Path to built exe (Windows). If missing, uses python -m assistant diagnose",
    )
    args = ap.parse_args()
    if args.exe.exists():
        # Windowed exe won't show stdout — prefer a console rebuild for CI later.
        # For now invoke python module smoke which matches packaging imports.
        print(f"NOTE: {args.exe} exists; running module diagnose (windowed exe has no console).")
    cmd = [sys.executable, "-m", "assistant", "diagnose"]
    print(">>", " ".join(cmd))
    r = subprocess.run(cmd)
    if r.returncode == 2:
        print("SMOKE FAIL: voice deps missing (missing_dep) — reinstall requirements-voice.txt and rebuild.")
    elif r.returncode != 0:
        print(f"SMOKE FAIL: diagnose exited {r.returncode}")
    else:
        print("SMOKE PASS")
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
