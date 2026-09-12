"""Local Ollama / chat backend selection — no live Ollama required."""

from __future__ import annotations

import assistant.envload as envload
from assistant.llm.builtins import chat_reply


def test_prefer_local_llm_flag(monkeypatch):
    monkeypatch.setenv("JARVIS_LOCAL_LLM", "1")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    assert envload.prefer_local_llm() is True


def test_prefer_local_from_base_url(monkeypatch):
    monkeypatch.setenv("JARVIS_LOCAL_LLM", "0")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:11434/v1")
    # Explicit off wins
    assert envload.prefer_local_llm() is False
    monkeypatch.delenv("JARVIS_LOCAL_LLM", raising=False)
    assert envload.prefer_local_llm() is True


def test_local_model_default(monkeypatch):
    monkeypatch.delenv("JARVIS_LOCAL_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    assert envload.local_model_name() == "llama3.2"
    monkeypatch.setenv("JARVIS_LOCAL_MODEL", "mistral")
    assert envload.local_model_name() == "mistral"


def test_openai_compatible_base(monkeypatch):
    monkeypatch.setenv("JARVIS_OLLAMA_URL", "http://127.0.0.1:11434")
    assert envload.openai_compatible_base().endswith("/v1")


def test_chat_backend_label_ollama(monkeypatch):
    monkeypatch.setenv("JARVIS_LOCAL_LLM", "1")
    monkeypatch.setattr(envload, "ollama_reachable", lambda timeout=0.6: True)
    assert envload.chat_backend_label(probe=True) == "chat:Ollama"


def test_chat_backend_label_offline(monkeypatch):
    monkeypatch.setenv("JARVIS_LOCAL_LLM", "0")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(envload, "ollama_reachable", lambda timeout=0.6: False)
    assert envload.chat_backend_label(probe=True) == "chat:offline"


def test_chat_reply_uses_local_without_cloud_key(monkeypatch):
    monkeypatch.setenv("JARVIS_LOCAL_LLM", "1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(envload, "ollama_reachable", lambda timeout=0.6: True)
    monkeypatch.setattr(envload, "prefer_local_llm", lambda: True)
    monkeypatch.setattr(envload, "local_llm_active", lambda probe=True: True)

    def fake_post(**kwargs):
        assert "11434" in kwargs["base"] or kwargs["base"].endswith("/v1")
        assert kwargs["model"]
        assert kwargs["api_key"]  # dummy ok
        return "Local hello"

    import assistant.llm.builtins as builtins

    monkeypatch.setattr(builtins, "_post_chat_completions", fake_post)
    assert chat_reply("hello there friend") == "Local hello"


def test_chat_reply_offline_tip_mentions_ollama(monkeypatch):
    monkeypatch.setenv("JARVIS_LOCAL_LLM", "0")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(envload, "ollama_reachable", lambda timeout=0.6: False)
    monkeypatch.setattr(envload, "local_llm_active", lambda probe=True: False)
    monkeypatch.setattr(envload, "prefer_local_llm", lambda: False)
    reply = chat_reply("tell me a joke about routers")
    assert "Ollama" in reply or "ollama" in reply.lower()


def test_wake_extra_variants():
    from assistant.voice.wake import WakeConfig, WakePipeline

    p = WakePipeline(config=WakeConfig(wake_name="Jarvis"))
    assert p.wake_at_start("jarvus what time")
    assert p.wake_at_start("gervis help")
