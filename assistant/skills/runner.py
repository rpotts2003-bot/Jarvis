"""Execute matched registry skills via catalog / teach / replies."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from assistant.actions.router import ActionRequest
from assistant.llm.intent import Intent, parse_intent
from assistant.skills.registry import (
    Skill,
    list_builtin_summaries,
    match_skill,
    normalize_utterance,
)

if TYPE_CHECKING:
    from assistant.core.orchestrator import Orchestrator, TurnResult

try:
    _TZ = ZoneInfo("Europe/London")
except Exception:  # noqa: BLE001
    _TZ = None


def _time_reply(text: str) -> str:
    now = datetime.now(_TZ) if _TZ else datetime.now()
    low = text.lower()
    if re.search(r"\bdate\b|\bday\b|\btoday\b", low):
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

    cleaned = normalize_utterance(text)
    hit = match_skill(cleaned)
    if not hit:
        return None
    skill, m = hit

    if skill.kind == "reply":
        if skill.id == "time_now":
            reply = _time_reply(cleaned)
        elif skill.id == "help":
            taught = [s.key for s in orch.memory.list_tier("skill")]
            reply = _help_reply(taught)
        elif skill.id == "diagnose_mic" or skill.reply_template == "__DIAGNOSE_MIC__":
            from assistant.voice.mic_health import mark_probed, probe_microphone

            result = probe_microphone()
            mark_probed(status=result.status.value)
            reply = "Microphone OK." if result.ok else (result.message + " Typing still works.")
        elif skill.reply_template:
            reply = skill.reply_template
        else:
            reply = skill.description or "OK."
        return orch._speak_result(TurnResult(reply=reply, intent=Intent("chat", reply=reply)))

    if skill.kind == "list":
        return orch._run_intent(Intent("list_skills", {}), confirmed=True)

    if skill.kind in {"teach", "forget"}:
        # Keep original text for teach parsers; wake word already stripped in cleaned
        return orch._run_intent(parse_intent(cleaned), confirmed=confirmed)

    if skill.kind == "action":
        action, params, clarify = _action_from_skill(skill, cleaned, m, orch)
        if clarify:
            return orch._speak_result(
                TurnResult(reply=clarify, intent=Intent("clarify", reply=clarify))
            )
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


def _map_browser_app(utterance: str, orch: Orchestrator) -> str:
    low = utterance.lower()
    allow = {a.lower() for a in getattr(orch.router, "allowlisted_apps", []) or []}
    if "edge" in low:
        if "edge" in allow:
            return "edge"
        if "msedge" in allow:
            return "msedge"
    if "chrome" in low and "chrome" in allow:
        return "chrome"
    # launch/open browser → prefer chrome then edge
    for cand in ("chrome", "edge", "msedge", "browser"):
        if cand in allow:
            return cand
    return "chrome"


def _action_from_skill(
    skill: Skill,
    text: str,
    m: re.Match[str],
    orch: Orchestrator,
) -> tuple[str | None, dict[str, Any], str | None]:
    """Returns (action, params, clarify_message)."""
    if skill.id == "volume":
        low = text.strip().lower()
        if low in {"mute", "volume mute"} or re.search(
            r"turn\s+(the\s+)?sound\s+off", low
        ):
            return "set_mute", {"muted": True}, None
        if low == "unmute" or re.search(r"turn\s+(the\s+)?sound\s+on", low):
            return "set_mute", {"muted": False}, None
        if re.fullmatch(r"volume", low):
            return None, {}, "What volume? Say a number from 0 to 100, or mute / unmute."
        g = m.group(1) if m.lastindex else None
        if g and str(g).isdigit():
            return "set_volume", {"level": int(g)}, None
        return None, {}, "What volume? Say a number from 0 to 100, or mute / unmute."

    if skill.id == "list_folder":
        path = ""
        if m.lastindex:
            path = (m.group(m.lastindex) or "").strip()
        # bare "list downloads" patterns have no group — detect from text
        low = text.strip().lower()
        for name in ("downloads", "documents", "desktop"):
            if re.search(rf"\b{name}\b", low):
                path = name
                break
        if not path or path.lower() in {"folder", "files", "file"}:
            return (
                None,
                {},
                "Which folder? Try: list downloads, list documents, or list desktop.",
            )
        aliases = {
            "downloads": str(Path.home() / "Downloads"),
            "documents": str(Path.home() / "Documents"),
            "desktop": str(Path.home() / "Desktop"),
        }
        key = path.lower().strip()
        resolved = aliases.get(key, path)
        if resolved.startswith("~"):
            resolved = str(Path(resolved).expanduser())
        return "list_files", {"path": resolved}, None

    if skill.id == "open_url":
        raw = (m.group(1) if m.lastindex else "").strip()
        if not raw.startswith("http"):
            raw = "https://" + raw
        return "open_url", {"url": raw}, None

    if skill.id == "open_browser":
        app = _map_browser_app(text, orch)
        return "open_app", {"app": app}, None

    if skill.id == "open_calculator":
        return "open_app", {"app": "calculator"}, None

    if skill.action:
        return skill.action, dict(skill.params), None

    return None, {}, None
