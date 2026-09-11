from pathlib import Path

from assistant.actions.router import ActionRequest, ActionRouter
from assistant.llm.intent import parse_intent


def test_parse_plex_intents():
    i = parse_intent(r'add C:\Videos\film.mp4 to plex')
    assert i.kind == "add_to_plex"
    assert "film.mp4" in i.params["source"]
    assert parse_intent("scan plex").kind == "plex_scan"


def test_add_to_plex_copy_and_blocks(tmp_path: Path):
    src_root = tmp_path / "downloads"
    lib = tmp_path / "plexmovies"
    src_root.mkdir()
    lib.mkdir()
    src = src_root / "Owned Movie.mp4"
    src.write_bytes(b"fake")
    scans: list[str] = []

    r = ActionRouter(
        allowlisted_apps=[],
        allowlisted_domains=[],
        folder_roots=[src_root],
        plex_library_dir=lib,
        plex_scan_fn=lambda: scans.append("scanned") or "scan ok",
    )
    pending = r.dispatch(ActionRequest("add_to_plex", {"source": str(src)}))
    assert pending.blocked_reason == "confirm_required"
    ok = r.dispatch(ActionRequest("add_to_plex", {"source": str(src)}, confirmed=True))
    assert ok.ok
    assert (lib / "Owned Movie.mp4").exists()
    assert scans == ["scanned"]

    blocked = r.dispatch(
        ActionRequest("add_to_plex", {"source": "https://example.com/a.mp4"}, confirmed=True)
    )
    assert blocked.blocked_reason == "scheme"

    outside = tmp_path / "secret" / "x.mp4"
    outside.parent.mkdir()
    outside.write_bytes(b"x")
    deny = r.dispatch(ActionRequest("add_to_plex", {"source": str(outside)}, confirmed=True))
    assert deny.blocked_reason == "allowlist"
