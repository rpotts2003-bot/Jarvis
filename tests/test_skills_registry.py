from pathlib import Path

from assistant.actions.router import ActionRouter
from assistant.core.orchestrator import Orchestrator
from assistant.memory.store import MemoryStore
from assistant.skills.registry import match_skill, normalize_utterance, seed_builtins
from assistant.ui.ring_timing import RingTiming
from assistant.voice.state_machine import VoiceState


def _orch(tmp: Path, apps: list[str] | None = None):
    opened: list[str] = []
    orch = Orchestrator(
        memory=MemoryStore(tmp / "m.db"),
        router=ActionRouter(
            allowlisted_apps=apps or ["calculator", "chrome", "edge"],
            allowlisted_domains=["example.com"],
            folder_roots=[tmp, Path.home() / "Downloads"],
            open_app_fn=opened.append,
        ),
    )
    return orch, opened


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
        "diagnose_mic",
    }:
        assert need in ids


def test_wake_word_stripped():
    assert normalize_utterance("Jarvis, help").lower() == "help"
    assert match_skill("hey jarvis what time is it")[0].id == "time_now"


def test_trigger_table_samples():
    assert match_skill("what can you do")[0].id == "help"
    assert match_skill("how do I use you")[0].id == "help"
    assert match_skill("show skills")[0].id == "list_skills"
    assert match_skill("launch calculator")[0].id == "open_calculator"
    assert match_skill("open edge")[0].id == "open_browser"
    assert match_skill("go to example.com")[0].id == "open_url"
    assert match_skill("open example.com")[0].id == "open_url"  # not browser
    assert match_skill("turn sound off")[0].id == "volume"
    assert match_skill("scan plex")[0].id == "plex_scan_reminder"
    assert match_skill("remember that my name is Sam")[0].id == "remember_that"


def test_volume_without_number_asks(tmp_path: Path):
    orch, _ = _orch(tmp_path)
    t = orch.handle_utterance("volume")
    assert "0 to 100" in t.reply


def test_list_folder_without_name_asks(tmp_path: Path):
    orch, _ = _orch(tmp_path)
    t = orch.handle_utterance("list files")
    assert "Which folder" in t.reply


def test_orchestrator_help(tmp_path: Path):
    orch, _ = _orch(tmp_path)
    t = orch.handle_utterance("help")
    assert "Built-in skills" in t.reply


def test_orchestrator_open_calc(tmp_path: Path):
    orch, apps = _orch(tmp_path)
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
