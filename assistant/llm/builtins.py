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

# Local chat must never hang the HUD forever (GUI runs this off the Tk thread).
_OLLAMA_TIMEOUT_S = 45.0
_BUNDLED_TIMEOUT_S = 45.0
_CLOUD_TIMEOUT_S = 30.0

_ADDRESS_RE = re.compile(
    r"^\s*(?:(?:when\s+i\s+(?:talk|speak)\s+to\s+you|please)\s+)?"
    r"(?:call\s+me|address\s+me\s+as|refer\s+to\s+me\s+as)\s+"
    r"['\"]?(.+?)['\"]?\s*[.!?]?\s*$",
    re.I,
)


def get_address_as() -> str:
    """Preferred form of address (e.g. sir). Prefs, then JARVIS_ADDRESS_AS env."""
    try:
        from assistant.voice.mic_health import load_prefs

        pref = str(load_prefs().get("address_as") or "").strip()
        if pref:
            return pref
    except Exception:
        pass
    return os.environ.get("JARVIS_ADDRESS_AS", "").strip()


def set_address_as(name: str) -> str:
    """Persist address preference to ui_prefs. Returns cleaned name."""
    cleaned = (name or "").strip().strip("\"'").rstrip(".!?").strip()
    if not cleaned:
        raise ValueError("empty address")
    # Keep short (title-ish forms: sir, ma'am, Captain…)
    if len(cleaned) > 40:
        cleaned = cleaned[:40].strip()
    from assistant.voice.mic_health import save_prefs

    save_prefs({"address_as": cleaned})
    return cleaned


def _seed_address_from_env() -> None:
    """If env sets JARVIS_ADDRESS_AS and prefs empty, write once."""
    env = os.environ.get("JARVIS_ADDRESS_AS", "").strip()
    if not env:
        return
    try:
        from assistant.voice.mic_health import load_prefs, save_prefs

        if not str(load_prefs().get("address_as") or "").strip():
            save_prefs({"address_as": env})
    except Exception:
        pass


def try_builtin(text: str, *, open_app: Callable[[str], str] | None = None) -> str | None:
    """Return a built-in reply, or None to fall through to intent/actions.

    open_app is accepted for API compatibility but unused — opens go through the router.
    """
    t = (text or "").strip()
    low = t.lower()

    # Address preference — durable, no confirm step
    m = _ADDRESS_RE.match(t)
    if m:
        try:
            name = set_address_as(m.group(1))
        except ValueError:
            return "What should I call you?"
        # Natural confirm: "Yes, sir." / "Yes, Captain."
        return f"Yes, {name}."

    if re.match(r"^(hi|hello|hey|good (morning|afternoon|evening))\b", low):
        addr = get_address_as()
        if addr:
            return f"Hello, {addr}. I’m Jarvis. Ask me anything, or say help to see what I can do."
        return "Hello. I’m Jarvis. Ask me anything, or say help to see what I can do."

    if re.search(r"\b(how are you|how's it going|you ok)\b", low):
        addr = get_address_as()
        if addr:
            return f"All systems nominal, {addr}. How can I help?"
        return "All systems nominal. How can I help?"

    if low in {"help", "what can you do", "commands", "?"} or "what can you do" in low:
        return (
            "I can chat, tell the time/date, open Calculator or Chrome, "
            "add a local video file to your Plex folder, scan Plex, and learn shortcuts "
            "like: learn when I say morning do open calculator. "
            "Say call me sir to set how I address you. "
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
        addr = get_address_as()
        return f"You’re welcome, {addr}." if addr else "You’re welcome."

    if re.search(r"\b(goodbye|bye|see you|good night)\b", low):
        addr = get_address_as()
        return f"Goodbye, {addr}. I’ll be here when you need me." if addr else "Goodbye. I’ll be here when you need me."

    return None


def _chat_messages(text: str, history: list[tuple[str, str]] | None) -> list[dict[str, str]]:
    _seed_address_from_env()
    system = (
        "You are Jarvis, a concise helpful desktop assistant for a UK user. "
        "Keep replies short (1–3 sentences). Do not claim you executed PC actions "
        "unless the user message says an action already ran."
    )
    address = get_address_as()
    if address:
        system += f" Always address the user as {address}."
    messages = [{"role": "system", "content": system}]
    for role, content in (history or [])[-6:]:
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": text})
    return messages


def _post_chat_completions(
    *,
    base: str,
    model: str,
    messages: list[dict[str, str]],
    api_key: str | None,
    timeout: float = 60.0,
) -> str:
    import json
    import urllib.request

    body = json.dumps(
        {"model": model, "messages": messages, "temperature": 0.6, "stream": False}
    ).encode()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(
        f"{base.rstrip('/')}/chat/completions",
        data=body,
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        data = json.loads(resp.read().decode())
    return data["choices"][0]["message"]["content"].strip()


def _format_local_chat_error(exc: BaseException, *, model: str) -> str:
    """Human caption for Ollama failures — never leave the HUD guessing."""
    err = str(exc) or exc.__class__.__name__
    low = err.lower()
    if isinstance(exc, TimeoutError) or "timed out" in low or "timeout" in low:
        return (
            f"Ollama timed out after {_OLLAMA_TIMEOUT_S:.0f}s. "
            "Is the model loaded? Try: ollama run "
            f"{model} \"hi\" — or ask for help / time / date."
        )
    # Model missing / not pulled
    if any(
        s in low
        for s in (
            "not found",
            "does not exist",
            "model '",
            "no such model",
            "pull",
            "404",
            "failed to load",
            "unknown model",
        )
    ):
        return (
            f"Ollama is running but model '{model}' is missing. "
            f"In a terminal run: ollama pull {model}"
        )
    if any(s in low for s in ("connection refused", "actively refused", "failed to establish", "111", "10061")):
        return (
            "Ollama is not running. Start Ollama (system tray / `ollama serve`), "
            f"then `ollama pull {model}` — or ask for help / time / date."
        )
    return (
        f"Local chat failed ({err[:120]}). Is Ollama running? "
        f"Install from https://ollama.com then: ollama pull {model} "
        "— or ask for help / time / date."
    )


def _try_bundled_local(messages: list[dict[str, str]]) -> str | None:
    """Prefer Jarvis-managed GGUF. Returns reply, a short status string, or None to fall through."""
    from assistant.llm import local_model as lm

    if lm.local_llm_disabled():
        return None

    state = lm.ensure_model_async()
    if state == "downloading" or (not lm.model_ready() and lm.download_in_progress()):
        return "Downloading brain… try again in a minute."
    if not lm.model_ready():
        # Download just kicked off or failed to start
        if state == "downloading":
            return "Downloading brain… try again in a minute."
        return None

    if not lm.llama_cpp_available():
        return (
            "Brain file is ready, but llama-cpp-python is not installed. "
            "Re-run Start Jarvis.bat (it tries to install the CPU wheel), "
            "or ask for help / time / date."
        )

    try:
        return lm.generate(messages, max_tokens=256, temperature=0.6)
    except Exception as e:  # noqa: BLE001
        err = str(e)[:160]
        return (
            f"Bundled chat failed ({err}). "
            "Built-ins like help / time / date still work."
        )


def chat_reply(text: str, *, history: list[tuple[str, str]] | None = None) -> str:
    """Free-form chat: bundled GGUF → optional Ollama (explicit) → optional cloud → tip."""
    from assistant.envload import (
        cloud_chat_enabled,
        local_model_name,
        ollama_reachable,
        openai_compatible_base,
        prefer_local_llm,
    )

    messages = _chat_messages(text, history)
    model = local_model_name()

    # 1) Bundled GGUF managed by Jarvis (preferred — no separate AI app)
    bundled = _try_bundled_local(messages)
    if bundled is not None:
        return bundled

    # 2) Ollama ONLY when JARVIS_LOCAL_LLM=1 explicitly (never auto)
    if prefer_local_llm():
        if not ollama_reachable(timeout=0.8):
            if not cloud_chat_enabled():
                return (
                    "Ollama is not running (nothing on :11434). "
                    "Start Ollama, then: ollama pull llama3.2 — "
                    "or wait for Jarvis’s own brain download, or ask for help / time / date."
                )
        else:
            try:
                base = openai_compatible_base()
                key = os.environ.get("OPENAI_API_KEY", "").strip() or "ollama"
                return _post_chat_completions(
                    base=base,
                    model=model,
                    messages=messages,
                    api_key=key,
                    timeout=_OLLAMA_TIMEOUT_S,
                )
            except Exception as e:  # noqa: BLE001
                if not cloud_chat_enabled():
                    return _format_local_chat_error(e, model=model)

    # 3) Optional cloud OpenAI-compatible provider (key must be set)
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if cloud_chat_enabled() and key:
        try:
            base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
            # Don't retry a dead Ollama URL as "cloud"
            if "11434" in base or "ollama" in base.lower():
                base = "https://api.openai.com/v1"
                cloud_model = "gpt-4o-mini"
            else:
                cloud_model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
            return _post_chat_completions(
                base=base,
                model=cloud_model,
                messages=messages,
                api_key=key,
                timeout=_CLOUD_TIMEOUT_S,
            )
        except Exception as e:  # noqa: BLE001
            err = str(e)
            if "429" in err or "Too Many Requests" in err:
                return (
                    "Chat hit a rate limit or billing cap (429). Check provider billing — "
                    "or wait for Jarvis’s bundled brain, or ask for help / time / date."
                )
            return f"I couldn’t reach the chat service ({e}). Try again, or ask for help / time / date."

    # 4) Offline tip
    from assistant.llm.local_model import DEFAULT_MODEL_SIZE_GB

    return (
        "I understood you, but free-form chat needs Jarvis’s brain file "
        f"(~{DEFAULT_MODEL_SIZE_GB:.1f} GB, downloads on first chat) or an optional cloud key. "
        "Built-ins like time, date, help still work. "
        "Say hi / help / what time is it — or wait a minute if a download just started."
    )
