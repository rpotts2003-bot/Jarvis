from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable


class Risk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    DESTRUCTIVE = "destructive"


@dataclass(frozen=True)
class ActionSpec:
    id: str
    risk: Risk
    description: str


CATALOG: dict[str, ActionSpec] = {
    "open_app": ActionSpec("open_app", Risk.LOW, "Open an allowlisted application"),
    "open_url": ActionSpec("open_url", Risk.MEDIUM, "Open an https URL"),
    "type_text": ActionSpec("type_text", Risk.MEDIUM, "Type text into the focused window"),
    "list_files": ActionSpec("list_files", Risk.LOW, "List files under an approved folder root"),
    "set_volume": ActionSpec("set_volume", Risk.LOW, "Set system volume 0-100"),
    "set_mute": ActionSpec("set_mute", Risk.LOW, "Mute or unmute system audio"),
}

BLOCKED_ACTIONS = frozenset(
    {"delete_file", "run_shell", "shell", "send_message", "install", "shutdown"}
)
