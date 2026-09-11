"""Run before every push. Exit non-zero if anything is shaky."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str]) -> None:
    print(f"\n>> {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode != 0:
        raise SystemExit(r.returncode)


def main() -> None:
    py = sys.executable
    run([py, str(ROOT / "scripts" / "check_self_methods.py")])
    run([py, "-m", "pytest", "-q"])
    run([py, "-m", "assistant", "scenarios"])
    # Syntax-compile all assistant modules (no import of tkinter required for .py compile)
    run([py, "-m", "compileall", "-q", str(ROOT / "assistant")])
    print("\nPREFLIGHT PASSED")


if __name__ == "__main__":
    main()
