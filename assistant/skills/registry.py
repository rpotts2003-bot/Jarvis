"""Built-in + user skill registry (Agent Brain pack + trigger tables)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

SkillKind = Literal["reply", "action", "teach", "forget", "list", "clarify"]

_WAKE = re.compile(r"^(?:hey\s+)?jarvis\b[\s,:]+", re.I)


@dataclass
class Skill:
    id: str
    triggers: list[str]
    kind: SkillKind
    builtin: bool = True
    enabled: bool = True
    description: str = ""
    action: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    reply_template: str | None = None


# Order matters for overlapping patterns: open_url before open_browser.
_BUILTIN: list[Skill] = [
    Skill(
        id="help",
        triggers=[
            r"^\s*help\s*$",
            r"^\s*what can you do\s*\??\s*$",
            r"^\s*what do you do\s*\??\s*$",
            r"^\s*commands\s*$",
            r"^\s*how do i use you\s*\??\s*$",
            r"^\s*\?\s*$",
        ],
        kind="reply",
        description="What Jarvis can do (built-ins + how to teach)",
    ),
    Skill(
        id="list_skills",
        triggers=[
            r"^\s*list\s+skills\s*$",
            r"^\s*what\s+skills\s*$",
            r"^\s*show\s+skills\s*$",
            r"^\s*skills\s+list\s*$",
        ],
        kind="list",
        description="Names + one-line triggers for built-ins and taught skills",
    ),
    Skill(
        id="time_now",
        triggers=[
            r"^\s*what time is it\s*\??\s*$",
            r"^\s*what'?s the time\s*\??\s*$",
            r"^\s*current time\s*\??\s*$",
            r"^\s*date today\s*\??\s*$",
            r"^\s*what'?s today'?s date\s*\??\s*$",
            r"^\s*what('?s| is) the date\s*\??\s*$",
            r"^\s*what day is it\s*\??\s*$",
        ],
        kind="reply",
        description="Local time/date (Europe/London default)",
    ),
    Skill(
        id="open_url",
        triggers=[
            r"^\s*open\s+url\s+(https?://\S+|\S+)\s*$",
            r"^\s*open\s+(https?://\S+)\s*$",
            r"^\s*go\s+to\s+(https?://\S+|(?:[a-z0-9-]+\.)+[a-z]{2,})\s*$",
            r"^\s*browse\s+(https?://\S+|(?:[a-z0-9-]+\.)+[a-z]{2,})\s*$",
            r"^\s*open\s+((?:[a-z0-9-]+\.)+[a-z]{2,}(?:/\S*)?)\s*$",
        ],
        kind="action",
        action="open_url",
        description="Open an https URL (allowlist / confirm gates)",
    ),
    Skill(
        id="open_calculator",
        triggers=[
            r"^\s*open\s+calculator\s*$",
            r"^\s*launch\s+calculator\s*$",
            r"^\s*start\s+calc\s*$",
            r"^\s*open\s+calc\s*$",
        ],
        kind="action",
        action="open_app",
        params={"app": "calculator"},
        description="Open Calculator",
    ),
    Skill(
        id="open_browser",
        triggers=[
            r"^\s*open\s+(browser|chrome|edge)\s*$",
            r"^\s*launch\s+browser\s*$",
            r"^\s*open\s+the\s+browser\s*$",
        ],
        kind="action",
        action="open_app",
        params={"app": "chrome"},
        description="Open browser (chrome/edge mapped to allowlisted app_ids)",
    ),
    Skill(
        id="volume",
        triggers=[
            r"^\s*set\s+volume\s+(?:to\s+)?(\d{1,3})\s*$",
            r"^\s*volume\s+(\d{1,3})\s*$",
            r"^\s*volume\s+mute\s*$",
            r"^\s*(mute|unmute)\s*$",
            r"^\s*turn\s+(the\s+)?sound\s+off\s*$",
            r"^\s*turn\s+(the\s+)?sound\s+on\s*$",
            r"^\s*volume\s*$",  # clarify — ask 0–100
        ],
        kind="action",
        description="Set volume or mute/unmute",
    ),
    Skill(
        id="list_folder",
        triggers=[
            r"^\s*list\s+downloads\s*$",
            r"^\s*list\s+documents\s*$",
            r"^\s*list\s+desktop\s*$",
            r"^\s*list\s+(?:files\s+)?(?:in\s+)?(.+)$",
            r"^\s*what'?s\s+in\s+(.+)$",
            r"^\s*what is in\s+(.+)$",
            r"^\s*show\s+files\s+in\s+(.+)$",
            r"^\s*list\s+folder\s*$",
            r"^\s*list\s+files\s*$",
        ],
        kind="action",
        action="list_files",
        description="List files under an allowlisted folder root",
    ),
    Skill(
        id="plex_scan_reminder",
        triggers=[
            r"^\s*scan\s+plex\s*$",
            r"^\s*plex\s+scan\s*$",
            r"^\s*remind me how to scan plex\s*$",
            r"^\s*how do i scan plex\s*\??\s*$",
        ],
        kind="reply",
        description="Plex setup reminder (text stub only)",
        reply_template=(
            "I won’t control or download for Plex from the web. "
            "Set plex.library_dir in config.yaml, keep media under an allowlisted folder, "
            "then say: add C:\\path\\to\\movie.mp4 to plex. "
            "When you’re ready for a real library refresh hook, we can wire that next."
        ),
    ),
    Skill(
        id="diagnose_mic",
        triggers=[
            r"^\s*diagnose(\s+mic(rophone)?)?\s*$",
            r"^\s*test(\s+my)?\s+mic(rophone)?\s*$",
            r"^\s*mic(\s+check|\s+test)?\s*$",
        ],
        kind="reply",
        description="Probe microphone and show fix hints",
        reply_template="__DIAGNOSE_MIC__",
    ),
    Skill(
        id="remember_that",
        triggers=[
            r"^\s*remember\s+that\b.+$",
            r"^\s*remember\s+this\b.+$",
            r"^\s*teach\s+(?:you|me)\b.+$",
            r"^\s*save\s+that\b.+$",
            r"^\s*learn\b.+$",
            r"^\s*next time\b.+$",
            r"^\s*remember\b.+$",
        ],
        kind="teach",
        description="Start teach/confirm flow (not a silent write)",
    ),
    Skill(
        id="forget_that",
        triggers=[
            r"^\s*forget\s+that\b.+$",
            r"^\s*forget\b.+$",
            r"^\s*stop\s+remembering\b.+$",
        ],
        kind="forget",
        description="Start forget/confirm flow",
    ),
]


def normalize_utterance(text: str) -> str:
    """Case-insensitive ready string; strip wake word if still present."""
    t = (text or "").strip()
    t = _WAKE.sub("", t).strip()
    return t


def seed_builtins() -> list[Skill]:
    return [Skill(**{**s.__dict__}) for s in _BUILTIN]


def _looks_like_url_or_domain(text: str) -> bool:
    t = text.strip()
    if re.search(r"https?://", t, re.I):
        return True
    if re.search(r"\b(?:go\s+to|browse|open\s+url)\b", t, re.I):
        return True
    # open example.com
    if re.match(r"^\s*open\s+((?:[a-z0-9-]+\.)+[a-z]{2,})", t, re.I):
        return True
    return False


def match_skill(
    text: str, skills: list[Skill] | None = None
) -> tuple[Skill, re.Match[str]] | None:
    t = normalize_utterance(text)
    if not t:
        return None
    skills = skills or seed_builtins()

    # Ambiguity: URL/domain present → prefer open_url over open_browser
    prefer_url = _looks_like_url_or_domain(t)

    for skill in skills:
        if not skill.enabled:
            continue
        if prefer_url and skill.id == "open_browser":
            continue
        for pat in skill.triggers:
            m = re.match(pat, t, re.I | re.S)
            if m:
                return skill, m
    return None


def list_builtin_summaries() -> list[str]:
    return [f"- {s.id}: {s.description}" for s in seed_builtins() if s.enabled]
