import pytest
from pathlib import Path

from assistant.memory.store import MemoryStore


def test_profile_roundtrip(tmp_path: Path):
    s = MemoryStore(tmp_path / "m.db")
    assert s.write("profile", "name", "Ada", confirmed=False) is None
    item = s.write("profile", "name", "Ada", confirmed=True)
    assert item and item.value == "Ada"
    assert s.get("profile", "name").value == "Ada"


def test_newest_wins(tmp_path: Path):
    s = MemoryStore(tmp_path / "m.db")
    s.write("profile", "city", "London", confirmed=True)
    s.write("profile", "city", "Manchester", confirmed=True)
    assert s.get("profile", "city").value == "Manchester"


def test_skill_and_episode(tmp_path: Path):
    s = MemoryStore(tmp_path / "m.db")
    s.write("skill", "morning", "open calculator", confirmed=True)
    assert s.get("skill", "morning").value == "open calculator"
    s.append_episode("did a thing", confirmed=True)
    eps = s.list_tier("episode")
    assert len(eps) == 1
    s.append_episode("another", confirmed=True)
    assert len(s.list_tier("episode")) == 2


def test_reject_empty_and_forget(tmp_path: Path):
    s = MemoryStore(tmp_path / "m.db")
    with pytest.raises(ValueError):
        s.write("profile", "", "x", confirmed=True)
    s.write("profile", "k", "v", confirmed=True)
    assert s.forget("profile", "k", confirmed=False) is False
    assert s.forget("profile", "k", confirmed=True) is True
    assert s.get("profile", "k") is None


def test_scope_isolation(tmp_path: Path):
    s = MemoryStore(tmp_path / "m.db")
    s.write("profile", "x", "profile-val", confirmed=True)
    s.write("skill", "x", "skill-val", confirmed=True)
    assert s.get("profile", "x").value == "profile-val"
    assert s.get("skill", "x").value == "skill-val"
