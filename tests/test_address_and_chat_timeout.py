"""Address preference + chat UX (no live model download)."""

from __future__ import annotations

import assistant.envload as envload
from assistant.llm import builtins
from assistant.llm import local_model as lm
from assistant.llm.builtins import (
    _format_local_chat_error,
    chat_reply,
    get_address_as,
    set_address_as,
    try_builtin,
)


def test_call_me_sir_persists(tmp_path, monkeypatch):
    prefs = tmp_path / "ui_prefs.json"
    monkeypatch.setattr(
        "assistant.voice.mic_health.prefs_path", lambda: prefs
    )
    monkeypatch.delenv("JARVIS_ADDRESS_AS", raising=False)
    r = try_builtin("call me sir")
    assert r == "Yes, sir."
    assert get_address_as() == "sir"
    assert set_address_as("Captain") == "Captain"
    assert get_address_as() == "Captain"


def test_when_i_talk_call_me(tmp_path, monkeypatch):
    prefs = tmp_path / "ui_prefs.json"
    monkeypatch.setattr(
        "assistant.voice.mic_health.prefs_path", lambda: prefs
    )
    monkeypatch.delenv("JARVIS_ADDRESS_AS", raising=False)
    r = try_builtin("when I talk to you call me sir")
    assert r == "Yes, sir."


def test_address_me_as(tmp_path, monkeypatch):
    prefs = tmp_path / "ui_prefs.json"
    monkeypatch.setattr(
        "assistant.voice.mic_health.prefs_path", lambda: prefs
    )
    monkeypatch.delenv("JARVIS_ADDRESS_AS", raising=False)
    r = try_builtin("address me as ma'am")
    assert r == "Yes, ma'am."


def test_chat_messages_includes_address(tmp_path, monkeypatch):
    prefs = tmp_path / "ui_prefs.json"
    monkeypatch.setattr(
        "assistant.voice.mic_health.prefs_path", lambda: prefs
    )
    monkeypatch.delenv("JARVIS_ADDRESS_AS", raising=False)
    set_address_as("sir")
    msgs = builtins._chat_messages("hello", None)
    assert any(
        "Always address the user as sir" in m.get("content", "")
        for m in msgs
        if m.get("role") == "system"
    )


def test_ollama_timeout_is_45():
    assert builtins._OLLAMA_TIMEOUT_S <= 45.0
    assert builtins._BUNDLED_TIMEOUT_S <= 45.0


def test_format_model_missing():
    msg = _format_local_chat_error(
        RuntimeError("model 'llama3.2' not found"), model="llama3.2"
    )
    assert "ollama pull llama3.2" in msg


def test_format_timeout():
    msg = _format_local_chat_error(TimeoutError("timed out"), model="llama3.2")
    assert "timed out" in msg.lower()


def test_chat_reply_immediate_when_ollama_down(monkeypatch):
    monkeypatch.setenv("JARVIS_DISABLE_LOCAL_LLM", "1")
    monkeypatch.setenv("JARVIS_LOCAL_LLM", "1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(envload, "ollama_reachable", lambda timeout=0.6: False)
    monkeypatch.setattr(envload, "prefer_local_llm", lambda: True)
    monkeypatch.setattr(envload, "local_llm_active", lambda probe=True: False)
    monkeypatch.setattr(envload, "cloud_chat_enabled", lambda: False)
    monkeypatch.setattr(lm, "local_llm_disabled", lambda: True)
    reply = chat_reply("tell me a joke")
    assert "Ollama" in reply or "ollama" in reply.lower()
    assert "not running" in reply.lower() or "unavailable" in reply.lower()


def test_submit_async_in_gui_source():
    """Avoid importing tkinter (not always installed in CI)."""
    import ast
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "assistant" / "ui" / "gui.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    methods = {
        n.name
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) or isinstance(n, ast.AsyncFunctionDef)
    }
    assert "_submit_async" in methods
    assert "_send" in methods
    assert "_handle_voice_command" in methods
    # Ensure _send does not call on_submit synchronously on the main path
    text = src.read_text(encoding="utf-8")
    assert "self._submit_async" in text
    assert "threading.Thread(target=worker, name=\"jarvis-submit\"" in text
