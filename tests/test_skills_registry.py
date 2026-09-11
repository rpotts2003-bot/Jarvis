from pathlib import Path

from assistant.actions.router import ActionRouter
from assistant.core.orchestrator import Orchestrator
from assistant.memory.store import MemoryStore
from assistant.skills.registry import match_skill, seed_builtins
from assistant.ui.ring_timing import RingTiming
from assistant.voice.state_machine import VoiceState


def test_seed_has_core_builtins():
    ids = {s.id for s in seed_builtins()}
    for need in {
        "help",
        "list_skills",
        "time_now",
        "open_calculator",
        "open_browser",
        "open_url",
        "volume",
        "list_folder",
        "plex_scan_reminder",
        "remember_that",
        "forget_that",
    }:
        assert need in ids


def test_match_help_and_calc():
    assert match_skill("help")[0].id == "help"
    assert match_skill("open calculator")[0].id == "open_calculator"


def test_orchestrator_help(tmp_path: Path):
    orch = Orchestrator(
        memory=MemoryStore(tmp_path / "m.db"),
        router=ActionRouter(
            allowlisted_apps=["calculator", "chrome"],
            allowlisted_domains=["example.com"],
            folder_roots=[tmp_path],
        ),
    )
    t = orch.handle_utterance("help")
    assert "Built-in skills" in t.reply


def test_orchestrator_open_calc(tmp_path: Path):
    apps: list[str] = []
    orch = Orchestrator(
        memory=MemoryStore(tmp_path / "m.db"),
        router=ActionRouter(
            allowlisted_apps=["calculator", "chrome"],
            allowlisted_domains=[],
            folder_roots=[tmp_path],
            open_app_fn=apps.append,
        ),
    )
    t = orch.handle_utterance("open calculator")
    assert t.action_ok is True
    assert apps == ["calculator"]


def test_thinking_zeros_level_same_frame():
    r = RingTiming()
    r.set_state(VoiceState.LISTENING)
    r.set_level(0.9)
    r.set_state(VoiceState.THINKING)
    assert r._raw_level == 0.0
    assert r._smooth == 0.0


def test_barge_in_zeros_level_same_frame():
    r = RingTiming()
    r.set_state(VoiceState.SPEAKING)
    r.set_level(0.8)
    r.set_state(VoiceState.LISTENING, barge_in=True)
    assert r._raw_level == 0.0
