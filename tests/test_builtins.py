from pathlib import Path

from assistant.actions.router import ActionRouter
from assistant.core.orchestrator import Orchestrator
from assistant.llm.builtins import try_builtin
from assistant.memory.store import MemoryStore


def test_try_builtin_hello():
    r = try_builtin("hello")
    assert r and "Jarvis" in r


def test_try_builtin_help():
    r = try_builtin("help")
    assert r and "Plex" in r


def test_orchestrator_builtin_before_echo(tmp_path: Path):
    mem = MemoryStore(tmp_path / "m.db")
    router = ActionRouter(
        allowlisted_apps=["calculator"],
        allowlisted_domains=[],
        folder_roots=[tmp_path],
    )
    orch = Orchestrator(memory=mem, router=router)
    t = orch.handle_utterance("hi")
    assert "Jarvis" in t.reply
    assert "You said:" not in t.reply
