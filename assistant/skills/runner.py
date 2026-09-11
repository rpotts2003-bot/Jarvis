"""Execute matched registry skills via catalog / teach / replies."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from assistant.actions.router import ActionRequest
from assistant.llm.intent import Intent, parse_intent
from assistant.skills.registry import Skill, list_builtin_summaries, match_skill

if TYPE_CHECKING:
    from assistant.core.orchestrator import Orchestrator, TurnResult

try:
    _TZ = ZoneInfo("Europe/London")
except Exception:  # noqa: BLE001
    _TZ = None


def _time_reply(text: str) -> str:
    now = datetime.now(_TZ) if _TZ else datetime.now()
    low = text.lower()
    if re.search(r"\bdate\b|\bday\b", low):
        return f"Today is {now.strftime('%A, %d %B %Y')}."
    hour = now.hour % 12 or 12
    ampm = "AM" if now.hour < 12 else "PM"
    return f"It's {hour}:{now.minute:02d} {ampm}."


def _help_reply(taught: list[str] | None = None) -> str:
    lines = [
        "Built-in skills:",
        *list_builtin_summaries(),
        "",
        "Teach a shortcut: learn when I say morning do open calculator",
        "Free-form chat needs OPENAI_API_KEY; actions still work offline.",
    ]
    if taught:
        lines.append("Your skills: " + ", ".join(taught[:12]))
    return "\n".join(lines)


def try_registry_skill(
    orch: Orchestrator, text: str, *, confirmed: bool = False
) -> TurnResult | None:
    from assistant.core.orchestrator import TurnResult

    hit = match_skill(text)
    if not hit:
        return None
    skill, m = hit

    if skill.kind == "reply":
        if skill.id == "time_now":
            reply = _time_reply(text)
        elif skill.id == "help":
            taught = [s.key for s in orch.memory.list_tier("skill")]
            reply = _help_reply(taught)
        elif skill.reply_template:
            reply = skill.reply_template
        else:
            reply = skill.description or "OK."
        return orch._speak_result(TurnResult(reply=reply, intent=Intent("chat", reply=reply)))

    if skill.kind == "list":
        return orch._run_intent(Intent("list_skills", {}), confirmed=True)

    if skill.kind in {"teach", "forget"}:
        return orch._run_intent(parse_intent(text), confirmed=confirmed)

    if skill.kind == "action":
        action, params = _action_from_skill(skill, text, m)
        if action is None:
            return None
        req = ActionRequest(action=action, params=params, confirmed=confirmed)
        result = orch.router.dispatch(req)
        kind = action if action in {
            "open_app",
            "open_url",
            "list_files",
            "set_volume",
            "set_mute",
            "add_to_plex",
            "plex_scan",
            "type_text",
        } else "chat"
        intent = Intent(kind, params=params)  # type: ignore[arg-type]
        if result.blocked_reason == "confirm_required":
            orch.pending = {"type": "action", "request": req, "intent": intent}
            return TurnResult(
                reply=result.message,
                intent=intent,
                action_ok=False,
                pending_confirm=result.data,
            )
        reply = result.message if result.ok else f"Blocked: {result.message}"
        return orch._speak_result(
            TurnResult(reply=reply, intent=intent, action_ok=result.ok)
        )

    return None


def _action_from_skill(
    skill: Skill, text: str, m: re.Match[str]
) -> tuple[str | None, dict[str, Any]]:
    if skill.id == "volume":
        low = text.strip().lower()
        if low in {"mute", "unmute"}:
            return "set_mute", {"muted": low == "mute"}
        g = m.group(1) if m.lastindex else None
        if g and str(g).isdigit():
            return "set_volume", {"level": int(g)}
        return None, {}

    if skill.id == "list_folder":
        path = (m.group(m.lastindex) if m.lastindex else "").strip()
        aliases = {
            "downloads": str(Path.home() / "Downloads"),
            "documents": str(Path.home() / "Documents"),
            "desktop": str(Path.home() / "Desktop"),
        }
        key = path.lower().strip()
        path = aliases.get(key, path)
        if path.startswith("~"):
            path = str(Path(path).expanduser())
        return "list_files", {"path": path}

    if skill.id == "open_url":
        raw = (m.group(1) if m.lastindex else "").strip()
        if not raw.startswith("http"):
            raw = "https://" + raw
        return "open_url", {"url": raw}

    if skill.action:
        return skill.action, dict(skill.params)

    return None, {}
