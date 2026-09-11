from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


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
    "add_to_plex": ActionSpec(
        "add_to_plex",
        Risk.MEDIUM,
        "Copy or move a local media file into the approved Plex library folder",
    ),
    "plex_scan": ActionSpec(
        "plex_scan",
        Risk.LOW,
        "Request a Plex library refresh (local server hook)",
    ),
}

BLOCKED_ACTIONS = frozenset(
    {
        "delete_file",
        "run_shell",
        "shell",
        "send_message",
        "install",
        "shutdown",
        "download",
        "torrent",
        "pirate",
        "web_download",
    }
)
