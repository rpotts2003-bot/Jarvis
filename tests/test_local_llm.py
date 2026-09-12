"""Bundled GGUF / chat backend selection — no live HuggingFace or Ollama."""

from __future__ import annotations

import assistant.envload as envload
from assistant.llm import local_model as lm
from assistant.llm.builtins import chat_reply


def test_prefer_local_llm_flag(monkeypatch):
    monkeypatch.setenv("JARVIS_LOCAL_LLM", "1")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    assert envload.prefer_local_llm() is True


def test_prefer_local_no_auto_from_base_url(monkeypatch):
    """Ollama must NOT auto-activate from OPENAI_BASE_URL alone."""
    monkeypatch.delenv("JARVIS_LOCAL_LLM", raising=False)
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:11434/v1")
    assert envload.prefer_local_llm() is False
    monkeypatch.setenv("JARVIS_LOCAL_LLM", "0")
    assert envload.prefer_local_llm() is False


def test_local_model_default(monkeypatch):
    monkeypatch.delenv("JARVIS_LOCAL_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    assert envload.local_model_name() == "llama3.2"
    monkeypatch.setenv("JARVIS_LOCAL_MODEL", "mistral")
    assert envload.local_model_name() == "mistral"


def test_openai_compatible_base(monkeypatch):
    monkeypatch.setenv("JARVIS_OLLAMA_URL", "http://127.0.0.1:11434")
    assert envload.openai_compatible_base().endswith("/v1")


def test_chat_backend_label_local(monkeypatch, tmp_path):
    monkeypatch.setattr(lm, "user_data_dir", lambda: tmp_path)
    # Force models_dir under tmp
    monkeypatch.setattr(lm, "models_dir", lambda: tmp_path / "models")
    (tmp_path / "models").mkdir(parents=True)
    fake = tmp_path / "models" / lm.DEFAULT_MODEL_FILE
    fake.write_bytes(b"x" * (lm._MIN_BYTES + 10))
    monkeypatch.delenv("JARVIS_DISABLE_LOCAL_LLM", raising=False)
    monkeypatch.delenv("JARVIS_LOCAL_LLM", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    lm.reset_for_tests()
    assert envload.chat_backend_label(probe=False) == "chat:local"


def test_chat_backend_label_downloading(monkeypatch, tmp_path):
    monkeypatch.setattr(lm, "models_dir", lambda: tmp_path / "models")
    (tmp_path / "models").mkdir(parents=True)
    monkeypatch.setattr(lm, "model_ready", lambda: False)
    monkeypatch.setattr(lm, "download_in_progress", lambda: True)
    monkeypatch.setattr(lm, "ensure_model_async", lambda: "downloading")
    monkeypatch.delenv("JARVIS_DISABLE_LOCAL_LLM", raising=False)
    monkeypatch.delenv("JARVIS_LOCAL_LLM", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert envload.chat_backend_label(probe=True) == "chat:downloading"


def test_chat_backend_label_offline(monkeypatch):
    monkeypatch.setenv("JARVIS_DISABLE_LOCAL_LLM", "1")
    monkeypatch.setenv("JARVIS_LOCAL_LLM", "0")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(envload, "ollama_reachable", lambda timeout=0.6: False)
    assert envload.chat_backend_label(probe=True) == "chat:offline"


def test_chat_backend_label_ollama_only_when_forced(monkeypatch):
    monkeypatch.setenv("JARVIS_DISABLE_LOCAL_LLM", "1")
    monkeypatch.setenv("JARVIS_LOCAL_LLM", "1")
    monkeypatch.setattr(envload, "ollama_reachable", lambda timeout=0.6: True)
    assert envload.chat_backend_label(probe=True) == "chat:Ollama"


def test_model_path_helpers(monkeypatch, tmp_path):
    monkeypatch.setattr(lm, "models_dir", lambda: tmp_path / "models")
    monkeypatch.delenv("JARVIS_MODEL_FILE", raising=False)
    monkeypatch.delenv("JARVIS_MODEL_URL", raising=False)
    assert lm.model_file_name() == lm.DEFAULT_MODEL_FILE
    assert lm.DEFAULT_MODEL_FILE in lm.model_url()
    assert lm.model_path() == tmp_path / "models" / lm.DEFAULT_MODEL_FILE
    monkeypatch.setenv("JARVIS_MODEL_FILE", "custom.gguf")
    assert lm.model_file_name() == "custom.gguf"


def test_model_ready_size_gate(monkeypatch, tmp_path):
    monkeypatch.setattr(lm, "models_dir", lambda: tmp_path / "models")
    d = tmp_path / "models"
    d.mkdir()
    tiny = d / lm.DEFAULT_MODEL_FILE
    tiny.write_bytes(b"nope")
    monkeypatch.delenv("JARVIS_DISABLE_LOCAL_LLM", raising=False)
    assert lm.model_ready() is False
    tiny.write_bytes(b"x" * (lm._MIN_BYTES + 1))
    assert lm.model_ready() is True


def test_start_download_mocked(monkeypatch, tmp_path):
    monkeypatch.setattr(lm, "models_dir", lambda: tmp_path / "models")
    (tmp_path / "models").mkdir(parents=True)
    monkeypatch.delenv("JARVIS_DISABLE_LOCAL_LLM", raising=False)
    lm.reset_for_tests()

    called = {}

    def fake_worker(url, dest):
        called["url"] = url
        dest.write_bytes(b"x" * (lm._MIN_BYTES + 5))
        lm._write_status({"state": "ready", "file": dest.name, "message": "ok"})

    monkeypatch.setattr(lm, "_download_worker", fake_worker)
    assert lm.start_download() is True
    # Thread may still be spinning — join briefly
    t = lm._download_thread
    if t:
        t.join(timeout=2)
    assert called.get("url") == lm.model_url()
    assert lm.model_ready()


def test_chat_reply_bundled_preferred(monkeypatch):
    monkeypatch.delenv("JARVIS_DISABLE_LOCAL_LLM", raising=False)
    monkeypatch.delenv("JARVIS_LOCAL_LLM", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(lm, "local_llm_disabled", lambda: False)
    monkeypatch.setattr(lm, "ensure_model_async", lambda: "ready")
    monkeypatch.setattr(lm, "model_ready", lambda: True)
    monkeypatch.setattr(lm, "download_in_progress", lambda: False)
    monkeypatch.setattr(lm, "llama_cpp_available", lambda: True)
    monkeypatch.setattr(lm, "generate", lambda messages, **kw: "Bundled hello, sir.")
    assert chat_reply("hello there friend") == "Bundled hello, sir."


def test_chat_reply_downloading_message(monkeypatch):
    monkeypatch.delenv("JARVIS_DISABLE_LOCAL_LLM", raising=False)
    monkeypatch.setattr(lm, "local_llm_disabled", lambda: False)
    monkeypatch.setattr(lm, "ensure_model_async", lambda: "downloading")
    monkeypatch.setattr(lm, "model_ready", lambda: False)
    monkeypatch.setattr(lm, "download_in_progress", lambda: True)
    reply = chat_reply("tell me a joke about routers")
    assert "Downloading brain" in reply


def test_chat_reply_offline_tip_no_required_ollama(monkeypatch):
    monkeypatch.setenv("JARVIS_DISABLE_LOCAL_LLM", "1")
    monkeypatch.setenv("JARVIS_LOCAL_LLM", "0")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(envload, "ollama_reachable", lambda timeout=0.6: False)
    monkeypatch.setattr(envload, "prefer_local_llm", lambda: False)
    reply = chat_reply("tell me a joke about routers")
    assert "brain" in reply.lower() or "Built-ins" in reply or "help" in reply.lower()


def test_wake_extra_variants():
    from assistant.voice.wake import WakeConfig, WakePipeline

    p = WakePipeline(config=WakeConfig(wake_name="Jarvis"))
    assert p.wake_at_start("jarvus what time")
    assert p.wake_at_start("gervis help")
