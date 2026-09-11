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
