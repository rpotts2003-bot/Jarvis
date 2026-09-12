"""Load .env from project root and ~/.jarvis without requiring python-dotenv."""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from assistant.config import app_root, user_data_dir

_DEFAULT_OLLAMA = "http://127.0.0.1:11434"
_DEFAULT_LOCAL_MODEL = "llama3.2"


def _parse_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def load_env() -> None:
    # Next to frozen exe (user-editable), then bundle, then ~/.jarvis
    if getattr(sys, "frozen", False):
        _parse_env_file(Path(sys.executable).resolve().parent / ".env")
    _parse_env_file(app_root() / ".env")
    _parse_env_file(user_data_dir() / ".env")


def _truthy(val: str | None) -> bool:
    return (val or "").strip().lower() in {"1", "true", "yes", "on"}


def _falsy(val: str | None) -> bool:
    return (val or "").strip().lower() in {"0", "false", "no", "off"}


def ollama_base_url() -> str:
    """Return Ollama root (no /v1). Honours OPENAI_BASE_URL when it points at Ollama."""
    explicit = os.environ.get("JARVIS_OLLAMA_URL", "").strip().rstrip("/")
    if explicit:
        return explicit.replace("/v1", "") if explicit.endswith("/v1") else explicit
    base = os.environ.get("OPENAI_BASE_URL", "").strip().rstrip("/")
    if base and ("11434" in base or "ollama" in base.lower()):
        return base[:-3] if base.endswith("/v1") else base
    return _DEFAULT_OLLAMA


def openai_compatible_base(ollama_root: str | None = None) -> str:
    root = (ollama_root or ollama_base_url()).rstrip("/")
    return root if root.endswith("/v1") else f"{root}/v1"


def local_model_name() -> str:
    return (
        os.environ.get("JARVIS_LOCAL_MODEL", "").strip()
        or os.environ.get("OPENAI_MODEL", "").strip()
        or _DEFAULT_LOCAL_MODEL
    )


def ollama_reachable(timeout: float = 0.6) -> bool:
    """True if Ollama responds on /api/tags (or OpenAI-compatible models)."""
    root = ollama_base_url()
    for path in ("/api/tags", "/v1/models"):
        try:
            req = urllib.request.Request(
                f"{root}{path}",
                method="GET",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                if 200 <= getattr(resp, "status", 200) < 300:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            continue
        except Exception:
            continue
    return False


def prefer_local_llm() -> bool:
    """True only when user explicitly set JARVIS_LOCAL_LLM=1 (Ollama path).

    Bundled GGUF is separate — see bundled_local_* helpers. We do NOT auto-call
    Ollama just because something is listening on :11434.
    """
    if _falsy(os.environ.get("JARVIS_LOCAL_LLM")):
        return False
    return _truthy(os.environ.get("JARVIS_LOCAL_LLM"))


def local_llm_active(*, probe: bool = True) -> bool:
    """Use Ollama for chat only when JARVIS_LOCAL_LLM=1 and (optionally) reachable."""
    if not prefer_local_llm():
        return False
    return (not probe) or ollama_reachable()


def bundled_local_disabled() -> bool:
    return _truthy(os.environ.get("JARVIS_DISABLE_LOCAL_LLM"))


def bundled_local_ready() -> bool:
    """True when Jarvis-managed GGUF is on disk and not disabled."""
    if bundled_local_disabled():
        return False
    try:
        from assistant.llm.local_model import model_ready

        return model_ready()
    except Exception:
        return False


def bundled_local_downloading() -> bool:
    if bundled_local_disabled():
        return False
    try:
        from assistant.llm.local_model import download_in_progress, model_ready

        if model_ready():
            return False
        return download_in_progress()
    except Exception:
        return False


def chat_backend_label(*, probe: bool = True) -> str:
    """HUD status chip: chat:local | chat:downloading | chat:Ollama | chat:Grok | chat:OpenAI | chat:offline."""
    if bundled_local_disabled():
        # Fall through to optional Ollama / cloud / offline
        pass
    else:
        try:
            from assistant.llm import local_model as lm

            if lm.model_ready():
                return "chat:local"
            # Kick off download on first status probe so first launch starts early
            state = lm.ensure_model_async()
            if state == "downloading" or lm.download_in_progress():
                return "chat:downloading"
            if state == "ready":
                return "chat:local"
        except Exception:
            pass

    if local_llm_active(probe=probe):
        root = ollama_base_url().lower()
        if "11434" in root or "ollama" in root:
            return "chat:Ollama"
        return "chat:local"

    if cloud_chat_enabled():
        base = os.environ.get("OPENAI_BASE_URL", "").lower()
        if "x.ai" in base:
            return "chat:Grok"
        return "chat:OpenAI"
    return "chat:offline"


def cloud_chat_enabled() -> bool:
    """Cloud only when a key is explicitly set (and not forced off)."""
    flag = os.environ.get("JARVIS_CLOUD_CHAT", "1").strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return False
    return bool(os.environ.get("OPENAI_API_KEY", "").strip())
