from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

IntentKind = Literal[
    "teach",
    "recall",
    "forget",
    "list_skills",
    "open_app",
    "open_url",
    "list_files",
    "set_volume",
    "set_mute",
    "type_text",
    "add_to_plex",
    "plex_scan",
    "clarify",
    "chat",
]


@dataclass
class Intent:
    kind: IntentKind
    params: dict[str, Any] = field(default_factory=dict)
    reply: str | None = None


_SKILL_CMD = re.compile(
    r"^\s*(?:learn|remember|teach(?:\s+me)?|next time)\s+"
    r"(?:when\s+i\s+say|if\s+i\s+say|i\s+say)\s+"
    r"['\"]?(.+?)['\"]?\s*[,:]?\s*(?:do|then)\s+(.+)$",
    re.I | re.S,
)
_TEACH = re.compile(
    r"^\s*(?:remember(?:\s+that)?|teach(?:\s+me)?|learn(?:\s+that)?|next time(?:\s+that)?|if I say)\s+(.+)$",
    re.I | re.S,
)
_RECALL = re.compile(
    r"^\s*(?:what(?:'s| is)|recall|do you remember)\s+(.+?)\??\s*$", re.I
)
_FORGET = re.compile(r"^\s*forget\s+(.+)$", re.I)
_LIST_SKILLS = re.compile(
    r"^\s*(?:list\s+skills|what\s+can\s+you\s+do|show\s+skills)\s*$",
    re.I,
)
_OPEN_APP = re.compile(r"^\s*open\s+(?!https?://)([a-zA-Z0-9 _.-]+)\s*$", re.I)
_OPEN_URL = re.compile(r"^\s*open\s+(https?://\S+)\s*$", re.I)
_LIST = re.compile(r"^\s*list\s+(?:files\s+)?(?:in\s+)?(.+)$", re.I)
_VOL = re.compile(r"^\s*(?:set\s+)?volume\s+(?:to\s+)?(\d{1,3})\s*$", re.I)
_MUTE = re.compile(r"^\s*(mute|unmute)\s*$", re.I)
_TYPE = re.compile(r"^\s*type\s+(.+)$", re.I)
_ADD_PLEX = re.compile(
    r"^\s*add\s+(.+?)\s+to\s+plex(?:\s+library)?\s*$", re.I
)
_SCAN_PLEX = re.compile(r"^\s*(?:scan|refresh)\s+plex(?:\s+library)?\s*$", re.I)
_AMBIGUOUS_PC = re.compile(
    r"^\s*(do something(?:\s+to\s+my\s+(?:pc|computer))?|fix my (?:pc|computer)|make it work)\s*$", re.I
)


def parse_intent(text: str) -> Intent:
    t = (text or "").strip()
    if not t:
        return Intent("clarify", reply="I didn’t catch that — try again.")

    m = _SKILL_CMD.match(t)
    if m:
        return Intent(
            "teach",
            {
                "tier": "skill",
                "key": m.group(1).strip().lower(),
                "value": m.group(2).strip(),
            },
        )

    if _AMBIGUOUS_PC.match(t):
        return Intent(
            "clarify",
            reply="What should I do on your PC? For example: open Calculator, or set volume to 40.",
        )

    m = _TEACH.match(t)
    if m:
        body = m.group(1).strip()
        # skill form: when I say X, do Y
        skill = re.match(
            r"(?:when i say|if i say|next time i say)\s+['\"]?(.+?)['\"]?[,:]?\s*(?:do|then)\s+(.+)$",
            body,
            re.I | re.S,
        )
        if not skill:
            skill = re.match(
                r"['\"]?(.+?)['\"]?\s+means\s+(.+)$",
                body,
                re.I | re.S,
            )
        if skill:
            return Intent(
                "teach",
                {
                    "tier": "skill",
                    "key": skill.group(1).strip().lower(),
                    "value": skill.group(2).strip(),
                },
            )
        # profile: remember that my name is X / remember X is Y
        name = re.match(r"(?:that\s+)?(?:my\s+name\s+is|i am)\s+(.+)$", body, re.I)
        if name:
            return Intent(
                "teach",
                {"tier": "profile", "key": "name", "value": name.group(1).strip()},
            )
        kv = re.match(r"(?:that\s+)?(.+?)\s+is\s+(.+)$", body, re.I)
        if kv:
            return Intent(
                "teach",
                {
                    "tier": "profile",
                    "key": kv.group(1).strip().lower(),
                    "value": kv.group(2).strip(),
                },
            )
        return Intent(
            "teach",
            {"tier": "profile", "key": body[:80].lower(), "value": body},
        )

    m = _LIST_SKILLS.match(t)
    if m:
        return Intent("list_skills", {})

    m = _FORGET.match(t)
    if m:
        return Intent("forget", {"tier": "profile", "key": m.group(1).strip().lower()})

    m = _RECALL.match(t)
    if m:
        return Intent("recall", {"query": m.group(1).strip()})

    m = _OPEN_URL.match(t)
    if m:
        return Intent("open_url", {"url": m.group(1).strip()})

    m = _OPEN_APP.match(t)
    if m:
        return Intent("open_app", {"app": m.group(1).strip().lower()})

    m = _LIST.match(t)
    if m:
        return Intent("list_files", {"path": m.group(1).strip()})

    m = _VOL.match(t)
    if m:
        return Intent("set_volume", {"level": int(m.group(1))})

    m = _MUTE.match(t)
    if m:
        return Intent("set_mute", {"muted": m.group(1).lower() == "mute"})

    m = _TYPE.match(t)
    if m:
        return Intent("type_text", {"text": m.group(1)})

    m = _ADD_PLEX.match(t)
    if m:
        return Intent("add_to_plex", {"source": m.group(1).strip().strip('"').strip("'"), "mode": "copy"})

    m = _SCAN_PLEX.match(t)
    if m:
        return Intent("plex_scan", {})

    return Intent("chat", reply=f"You said: {t}")
