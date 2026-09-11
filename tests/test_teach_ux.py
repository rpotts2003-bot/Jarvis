from pathlib import Path

from assistant.actions.router import ActionRouter
from assistant.core.orchestrator import Orchestrator
from assistant.llm.intent import parse_intent
from assistant.memory.store import MemoryStore


def test_learn_skill_phrases():
    i = parse_intent("learn when I say morning do open calculator")
    assert i.kind == "teach" and i.params["tier"] == "skill"
    assert i.params["key"] == "morning"
    i2 = parse_intent("next time I say downloads, do open chrome")
    assert i2.kind == "teach" and i2.params["key"] == "downloads"
    assert parse_intent("list skills").kind == "list_skills"


def test_skill_runs_first_time_after_confirm(tmp_path: Path):
    apps: list[str] = []
    orch = Orchestrator(
        memory=MemoryStore(tmp_path / "m.db"),
        router=ActionRouter(
            allowlisted_apps=["calculator"],
            allowlisted_domains=[],
            folder_roots=[tmp_path],
            open_app_fn=apps.append,
        ),
    )
    orch.handle_utterance("learn when I say morning do open calculator")
    orch.handle_utterance("yes")
    r = orch.handle_utterance("morning")
    assert r.action_ok and apps == ["calculator"]
    skills = orch.handle_utterance("list skills")
    assert "morning" in skills.reply
