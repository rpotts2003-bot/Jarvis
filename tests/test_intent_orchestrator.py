from pathlib import Path

from assistant.actions.router import ActionRouter
from assistant.core.orchestrator import Orchestrator
from assistant.llm.intent import parse_intent
from assistant.memory.store import MemoryStore


def test_parse_basics():
    assert parse_intent("open calculator").kind == "open_app"
    assert parse_intent("open https://a.com").kind == "open_url"
    assert parse_intent("do something to my PC").kind == "clarify"
    assert parse_intent("remember that my name is Sam").params["key"] == "name"


def test_orchestrator_teach_confirm(tmp_path: Path):
    mem = MemoryStore(tmp_path / "m.db")
    router = ActionRouter(
        allowlisted_apps=["calculator"],
        allowlisted_domains=[],
        folder_roots=[tmp_path],
    )
    orch = Orchestrator(memory=mem, router=router)
    t = orch.handle_utterance("remember that my name is Sam")
    assert t.pending_confirm
    assert mem.get("profile", "name") is None
    t2 = orch.handle_utterance("yes")
    assert t2.memory_wrote
    assert mem.get("profile", "name").value == "Sam"


def test_freeform_what_is_is_chat():
    """Normal questions must not be classified as memory recall."""
    assert parse_intent("what is the capital of France?").kind == "chat"
    assert parse_intent("what's a good movie tonight").kind == "chat"
    assert parse_intent("what is quantum computing").kind == "chat"
    assert parse_intent("what is the weather like").kind == "chat"


def test_explicit_recall_still_matches():
    i = parse_intent("what is my name?")
    assert i.kind == "recall"
    assert "name" in i.params["query"].lower()
    assert i.params.get("text")
    assert parse_intent("what's my favorite color").kind == "recall"
    assert parse_intent("do you remember my name").kind == "recall"
    assert parse_intent("recall favorite color").kind == "recall"
    assert parse_intent("what did I tell you about wifi").kind == "recall"


def test_recall_hit_returns_saved_value(tmp_path: Path):
    mem = MemoryStore(tmp_path / "m.db")
    router = ActionRouter(
        allowlisted_apps=["calculator"],
        allowlisted_domains=[],
        folder_roots=[tmp_path],
    )
    orch = Orchestrator(memory=mem, router=router)
    orch.handle_utterance("remember that my name is Sam")
    orch.handle_utterance("yes")
    r = orch.handle_utterance("what is my name?")
    assert "Sam" in r.reply
    assert "don't have that saved" not in r.reply.lower()


def test_recall_miss_falls_through_to_chat(tmp_path: Path, monkeypatch):
    import assistant.core.orchestrator as orch_mod

    monkeypatch.setattr(orch_mod, "chat_reply", lambda text, history=None: f"CHAT:{text}")
    mem = MemoryStore(tmp_path / "m.db")
    router = ActionRouter(
        allowlisted_apps=["calculator"],
        allowlisted_domains=[],
        folder_roots=[tmp_path],
    )
    orch = Orchestrator(memory=mem, router=router)
    r = orch.handle_utterance("recall the unicorn protocol")
    assert r.reply.startswith("CHAT:")
    assert "don't have that saved" not in r.reply.lower()


def test_freeform_question_uses_chat_not_saved_yet(tmp_path: Path, monkeypatch):
    import assistant.core.orchestrator as orch_mod

    monkeypatch.setattr(orch_mod, "chat_reply", lambda text, history=None: f"CHAT:{text}")
    mem = MemoryStore(tmp_path / "m.db")
    router = ActionRouter(
        allowlisted_apps=["calculator"],
        allowlisted_domains=[],
        folder_roots=[tmp_path],
    )
    orch = Orchestrator(memory=mem, router=router)
    r = orch.handle_utterance("what is the capital of France?")
    assert r.intent.kind == "chat"
    assert r.reply.startswith("CHAT:")
    assert "don't have that saved" not in r.reply.lower()
