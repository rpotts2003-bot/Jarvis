"""Built-in skills and light conversation — no teaching required."""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Callable
from zoneinfo import ZoneInfo

# UK-friendly default; falls back if zoneinfo missing data
try:
    _TZ = ZoneInfo("Europe/London")
except Exception:  # noqa: BLE001
    _TZ = None


def try_builtin(text: str, *, open_app: Callable[[str], str] | None = None) -> str | None:
    """Return a built-in reply, or None to fall through to intent/actions.

    open_app is accepted for API compatibility but unused — opens go through the router.
    """
    t = (text or "").strip()
    low = t.lower()

    if re.match(r"^(hi|hello|hey|good (morning|afternoon|evening))\b", low):
        return "Hello. I’m Jarvis. Ask me anything, or say help to see what I can do."

    if re.search(r"\b(how are you|how's it going|you ok)\b", low):
        return "All systems nominal. How can I help?"

    if low in {"help", "what can you do", "commands", "?"} or "what can you do" in low:
        return (
            "I can chat, tell the time/date, open Calculator or Chrome, "
            "add a local video file to your Plex folder, scan Plex, and learn shortcuts "
            "like: learn when I say morning do open calculator. "
            "Most of the time, just talk to me in plain English."
        )

    if re.search(r"\b(what('?s| is) the )?time\b|\bwhat time is it\b", low):
        now = datetime.now(_TZ) if _TZ else datetime.now()
        hour = now.hour % 12 or 12
        ampm = "AM" if now.hour < 12 else "PM"
        return f"It’s {hour}:{now.minute:02d} {ampm}."

    if re.search(r"\b(what('?s| is) the )?date\b|\bwhat day is it\b", low):
        now = datetime.now(_TZ) if _TZ else datetime.now()
        return f"Today is {now.strftime('%A, %d %B %Y')}."

    if re.search(r"\b(who are you|what are you|your name)\b", low):
        return "I’m Jarvis — your desktop assistant. I run on your PC and remember what you teach me."

    if re.search(r"\bthank(s| you)\b", low):
        return "You’re welcome."

    if re.search(r"\b(goodbye|bye|see you|good night)\b", low):
        return "Goodbye. I’ll be here when you need me."

    return None


def chat_reply(text: str, *, history: list[tuple[str, str]] | None = None) -> str:
    """Free-form chat. Uses OpenAI-compatible API if OPENAI_API_KEY is set; else offline fallback."""
    from assistant.envload import cloud_chat_enabled
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not cloud_chat_enabled() or not key:
        return (
            "I understood you, but I need an API key for free-form chat. "
            "Set OPENAI_API_KEY in your environment (or .env), or ask me something built-in "
            "like time, date, help, or open calculator. You can also teach me shortcuts."
        )
    try:
        import json
        import urllib.request

        base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        messages = [
            {
                "role": "system",
                "content": (
                    "You are Jarvis, a concise helpful desktop assistant for a UK user. "
                    "Keep replies short (1–3 sentences). Do not claim you executed PC actions "
                    "unless the user message says an action already ran."
                ),
            }
        ]
        for role, content in (history or [])[-6:]:
            messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": text})
        body = json.dumps({"model": model, "messages": messages, "temperature": 0.6}).encode()
        req = urllib.request.Request(
            f"{base}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            data = json.loads(resp.read().decode())
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:  # noqa: BLE001
        return f"I couldn’t reach the chat service ({e}). Try again, or ask for help / time / date."
