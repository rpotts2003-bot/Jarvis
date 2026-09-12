"""Bundled GGUF brain — download + load + generate via llama-cpp-python.

No separate Ollama app. Model files live under ~/.jarvis/models/.
This is a language-model *file* Jarvis owns and manages (not a custom-trained GPT).
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from assistant.config import user_data_dir

# Default: Qwen2.5-1.5B-Instruct Q4_K_M (~1.04 GB) — small Windows-friendly instruct GGUF
DEFAULT_MODEL_FILE = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
DEFAULT_MODEL_URL = (
    "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/"
    + DEFAULT_MODEL_FILE
)
DEFAULT_MODEL_SIZE_GB = 1.04
_INFERENCE_TIMEOUT_S = 45.0
_MIN_BYTES = 1_000_000  # reject tiny / HTML error pages as "ready"

_lock = threading.Lock()
_download_thread: threading.Thread | None = None
_llm: Any = None
_llm_path: str | None = None


def models_dir() -> Path:
    d = user_data_dir() / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def status_path() -> Path:
    return models_dir() / "download_status.json"


def model_file_name() -> str:
    return os.environ.get("JARVIS_MODEL_FILE", "").strip() or DEFAULT_MODEL_FILE


def model_url() -> str:
    return os.environ.get("JARVIS_MODEL_URL", "").strip() or DEFAULT_MODEL_URL


def model_path() -> Path:
    return models_dir() / model_file_name()


def local_llm_disabled() -> bool:
    return (os.environ.get("JARVIS_DISABLE_LOCAL_LLM", "") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _write_status(payload: dict[str, Any]) -> None:
    payload = {**payload, "updated_at": time.time()}
    try:
        status_path().write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        pass


def read_status() -> dict[str, Any]:
    p = status_path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def model_ready() -> bool:
    """True when a usable GGUF file is on disk (size check only — no load)."""
    if local_llm_disabled():
        return False
    path = model_path()
    try:
        return path.is_file() and path.stat().st_size >= _MIN_BYTES
    except OSError:
        return False


def download_in_progress() -> bool:
    st = read_status()
    if st.get("state") == "downloading":
        return True
    global _download_thread
    with _lock:
        t = _download_thread
        return bool(t and t.is_alive())


def llama_cpp_available() -> bool:
    try:
        import llama_cpp  # noqa: F401

        return True
    except Exception:
        return False


def _download_worker(url: str, dest: Path) -> None:
    partial = dest.with_suffix(dest.suffix + ".partial")
    try:
        _write_status(
            {
                "state": "downloading",
                "url": url,
                "file": dest.name,
                "bytes_done": 0,
                "bytes_total": 0,
                "pct": 0.0,
                "message": "Downloading brain…",
            }
        )
        print(f"[jarvis] Downloading brain → {dest} …", flush=True)
        req = urllib.request.Request(url, headers={"User-Agent": "Jarvis/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            last_print = 0.0
            with partial.open("wb") as out:
                while True:
                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    out.write(chunk)
                    done += len(chunk)
                    pct = (100.0 * done / total) if total else 0.0
                    mb = done / (1024 * 1024)
                    now = time.time()
                    if now - last_print >= 1.0:
                        last_print = now
                        if total:
                            print(
                                f"[jarvis] Brain download {pct:5.1f}% "
                                f"({mb:.0f}/{total / (1024 * 1024):.0f} MB)",
                                flush=True,
                            )
                        else:
                            print(f"[jarvis] Brain download {mb:.0f} MB…", flush=True)
                    _write_status(
                        {
                            "state": "downloading",
                            "url": url,
                            "file": dest.name,
                            "bytes_done": done,
                            "bytes_total": total,
                            "pct": round(pct, 1),
                            "message": (
                                f"Downloading brain… {pct:.0f}%"
                                if total
                                else f"Downloading brain… {mb:.0f} MB"
                            ),
                        }
                    )
        if done < _MIN_BYTES:
            raise RuntimeError(f"Download too small ({done} bytes) — check URL")
        partial.replace(dest)
        _write_status(
            {
                "state": "ready",
                "url": url,
                "file": dest.name,
                "bytes_done": done,
                "bytes_total": done,
                "pct": 100.0,
                "message": "Brain ready",
            }
        )
        print(f"[jarvis] Brain ready ({done / (1024 * 1024):.0f} MB).", flush=True)
    except Exception as e:  # noqa: BLE001
        try:
            if partial.exists():
                partial.unlink()
        except OSError:
            pass
        err = str(e)[:200]
        _write_status(
            {
                "state": "error",
                "url": url,
                "file": dest.name,
                "message": f"Download failed: {err}",
                "error": err,
            }
        )
        print(f"[jarvis] Brain download failed: {err}", flush=True)


def start_download(*, force: bool = False) -> bool:
    """Start async download if model missing. Returns True if a download is/was started."""
    if local_llm_disabled():
        return False
    dest = model_path()
    if not force and model_ready():
        return False
    global _download_thread
    with _lock:
        if _download_thread and _download_thread.is_alive():
            return True
        url = model_url()
        t = threading.Thread(
            target=_download_worker,
            args=(url, dest),
            name="jarvis-model-download",
            daemon=True,
        )
        _download_thread = t
        t.start()
        return True


def ensure_model_async() -> str:
    """Ensure model is present or downloading. Returns status: ready|downloading|disabled|error|missing."""
    if local_llm_disabled():
        return "disabled"
    if model_ready():
        st = read_status()
        if st.get("state") != "ready":
            _write_status(
                {
                    "state": "ready",
                    "file": model_file_name(),
                    "message": "Brain ready",
                    "pct": 100.0,
                }
            )
        return "ready"
    if download_in_progress():
        return "downloading"
    st = read_status()
    if st.get("state") == "error":
        # Allow retry on next chat
        start_download()
        return "downloading"
    start_download()
    return "downloading"


def _get_llm() -> Any:
    global _llm, _llm_path
    path = str(model_path())
    with _lock:
        if _llm is not None and _llm_path == path:
            return _llm
        from llama_cpp import Llama

        # CPU-friendly defaults; n_gpu_layers=0 avoids CUDA surprises on Windows
        _llm = Llama(
            model_path=path,
            n_ctx=2048,
            n_threads=max(2, (os.cpu_count() or 4) // 2),
            n_gpu_layers=0,
            verbose=False,
        )
        _llm_path = path
        return _llm


def generate(
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 256,
    temperature: float = 0.6,
) -> str:
    """Run chat completion on the bundled GGUF. Raises if model/llama missing."""
    if local_llm_disabled():
        raise RuntimeError("Bundled local LLM disabled (JARVIS_DISABLE_LOCAL_LLM=1)")
    if not model_ready():
        raise RuntimeError("Model file not ready")
    if not llama_cpp_available():
        raise RuntimeError(
            "llama-cpp-python is not installed. "
            "Re-run Start Jarvis.bat (it tries to install it), "
            "or: pip install llama-cpp-python"
        )
    llm = _get_llm()
    # Prefer chat API when available
    try:
        out = llm.create_chat_completion(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return (out["choices"][0]["message"]["content"] or "").strip()
    except Exception:
        # Fallback: simple prompt concat
        parts: list[str] = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            parts.append(f"{role}: {content}")
        parts.append("assistant:")
        prompt = "\n".join(parts)
        out = llm(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=["user:", "\nuser:"],
        )
        text = out["choices"][0]["text"] if isinstance(out, dict) else str(out)
        return str(text).strip()


def reset_for_tests() -> None:
    """Clear in-memory LLM + download thread bookkeeping (unit tests only)."""
    global _llm, _llm_path, _download_thread
    with _lock:
        _llm = None
        _llm_path = None
        _download_thread = None
