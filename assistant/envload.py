"""Load .env from project root and ~/.jarvis without requiring python-dotenv."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from assistant.config import app_root, user_data_dir


def _parse_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def load_env() -> None:
    # Next to frozen exe (user-editable), then bundle, then ~/.jarvis
    if getattr(sys, "frozen", False):
        _parse_env_file(Path(sys.executable).resolve().parent / ".env")
    _parse_env_file(app_root() / ".env")
    _parse_env_file(user_data_dir() / ".env")


def cloud_chat_enabled() -> bool:
    flag = os.environ.get("JARVIS_CLOUD_CHAT", "1").strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return False
    return bool(os.environ.get("OPENAI_API_KEY", "").strip())
