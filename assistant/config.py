from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml


def app_root() -> Path:
    """Bundle root (PyInstaller) or project root."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[1]


def user_data_dir() -> Path:
    d = Path.home() / ".jarvis"
    d.mkdir(parents=True, exist_ok=True)
    return d


DEFAULT_CONFIG = app_root() / "config.yaml"


def load_config(path: Path | None = None) -> dict[str, Any]:
    # Prefer user override next to data dir, then bundled default
    user_cfg = user_data_dir() / "config.yaml"
    cfg_path = path or (user_cfg if user_cfg.exists() else DEFAULT_CONFIG)
    if not cfg_path.exists() and user_cfg.exists():
        cfg_path = user_cfg
    # First run: seed user config from bundle
    if path is None and not user_cfg.exists() and DEFAULT_CONFIG.exists():
        user_cfg.write_text(DEFAULT_CONFIG.read_text(encoding="utf-8"), encoding="utf-8")
        cfg_path = user_cfg
    with cfg_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("config root must be a mapping")
    return data


def expand_roots(roots: list[str]) -> list[Path]:
    return [Path(p).expanduser().resolve() for p in roots]
