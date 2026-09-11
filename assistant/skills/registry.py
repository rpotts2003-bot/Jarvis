"""Built-in + user skill registry (Agent Brain pack)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

SkillKind = Literal["reply", "action", "teach", "forget", "list"]


@dataclass
class Skill:
    id: str
    triggers: list[str]  # regex patterns, matched against full utterance (case-insensitive)
    kind: SkillKind
    builtin: bool = True
    enabled: bool = True
    description: str = ""
    # action pipeline: catalog action id + static/default params; utterance may fill params
    action: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    reply_template: str | None = None  # for reply-kind; may be filled by runner


# Seed pack — ship with app; editable/disableable later
_BUILTIN: list[Skill] = [
    Skill(
        id="help",
        triggers=[r"^\s*(help|commands|\?)\s*$", r"^\s*what can you do\s*\??\s*$"],
        kind="reply",
        description="What Jarvis can do (built-ins + how to teach)",
    ),
    Skill(
        id="list_skills",
        triggers=[r"^\s*list\s+skills\s*$", r"^\s*show\s+skills\s*$"],
        kind="list",
        description="Names + one-line triggers for built-ins and taught skills",
    ),
    Skill(
        id="time_now",
        triggers=[
            r"^\s*(what('?s| is) the )?time\s*\??\s*$",
            r"^\s*what time is it\s*\??\s*$",
            r"^\s*(what('?s| is) the )?date\s*\??\s*$",
            r"^\s*what day is it\s*\??\s*$",
        ],
        kind="reply",
        description="Local time/date (Europe/London default)",
    ),
    Skill(
        id="open_calculator",
        triggers=[
            r"^\s*open\s+(calculator|calc)\s*$",
            r"^\s*(calculator|calc)\s*$",
        ],
        kind="action",
        action="open_app",
        params={"app": "calculator"},
        description="Open Calculator",
    ),
    Skill(
        id="open_browser",
        triggers=[
            r"^\s*open\s+(browser|chrome)\s*$",
            r"^\s*open\s+the\s+browser\s*$",
        ],
        kind="action",
        action="open_app",
        params={"app": "chrome"},
        description="Open default browser (Chrome allowlist)",
    ),
    Skill(
        id="open_url",
        triggers=[
            r"^\s*open\s+(https?://\S+)\s*$",
            r"^\s*open\s+((?:[a-z0-9-]+\.)+[a-z]{2,})\s*$",
        ],
        kind="action",
        action="open_url",
        description="Open an https URL (allowlist / confirm gates)",
    ),
    Skill(
        id="volume",
        triggers=[
            r"^\s*(?:set\s+)?volume\s+(?:to\s+)?(\d{1,3})\s*$",
            r"^\s*(mute|unmute)\s*$",
        ],
        kind="action",
        description="Set volume or mute/unmute",
    ),
    Skill(
        id="list_folder",
        triggers=[
            r"^\s*list\s+(?:files\s+)?(?:in\s+)?(.+)$",
            r"^\s*what('?s| is) in\s+(.+)$",
        ],
        kind="action",
        action="list_files",
        description="List files under an allowlisted folder root",
    ),
    Skill(
        id="plex_scan_reminder",
        triggers=[
            r"^\s*(how do i (scan|use|set up) plex|plex (help|setup|reminder)|remind me about plex)\s*\??\s*$",
        ],
        kind="reply",
        description="Plex setup reminder (text); real scan via 'scan plex' when configured",
        reply_template=(
            "Plex works with files already on this PC — I won’t download from the web. "
            "Set plex.library_dir in config.yaml, keep media under an allowlisted folder, "
            "then say: add C:\\path\\to\\movie.mp4 to plex — or: scan plex — once the library path is set."
        ),
    ),
    Skill(
        id="remember_that",
        triggers=[
            r"^\s*(remember(?:\s+that)?|learn(?:\s+that)?|teach(?:\s+me)?)\b.+$",
            r"^\s*next time\b.+$",
        ],
        kind="teach",
        description="Start teach/confirm flow (not a silent write)",
    ),
    Skill(
        id="forget_that",
        triggers=[r"^\s*forget\s+.+$"],
        kind="forget",
        description="Start forget/confirm flow",
    ),
]


def seed_builtins() -> list[Skill]:
    return [Skill(**{**s.__dict__}) for s in _BUILTIN]  # shallow copy


def match_skill(text: str, skills: list[Skill] | None = None) -> tuple[Skill, re.Match[str]] | None:
    t = (text or "").strip()
    if not t:
        return None
    for skill in skills or seed_builtins():
        if not skill.enabled:
            continue
        for pat in skill.triggers:
            m = re.match(pat, t, re.I | re.S)
            if m:
                return skill, m
    return None


def list_builtin_summaries() -> list[str]:
    lines = []
    for s in seed_builtins():
        if not s.enabled:
            continue
        trig = s.triggers[0].replace(r"^\s*", "").replace(r"\s*$", "")[:40]
        lines.append(f"- {s.id}: {s.description}")
    return lines
