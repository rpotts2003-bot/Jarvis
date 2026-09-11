"""Local-file Plex library helpers. No web downloads."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Callable

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".m4v", ".wmv", ".mpeg", ".mpg"}


def add_local_file_to_plex(
    *,
    source: str,
    plex_library_dir: Path | None,
    approved_roots: list[Path],
    confirmed: bool,
    mode: str = "copy",
    overwrite: bool = False,
    scan_after: bool = True,
    copy_file_fn: Callable[[Path, Path], None] | None = None,
    move_file_fn: Callable[[Path, Path], None] | None = None,
    scan_fn: Callable[[], str] | None = None,
) -> dict[str, Any]:
    if plex_library_dir is None:
        return {
            "ok": False,
            "message": "Plex library folder is not configured in config.yaml",
            "blocked_reason": "config",
            "data": {},
        }
    raw_src = (source or "").strip()
    if not raw_src:
        return {
            "ok": False,
            "message": "Missing source file path",
            "blocked_reason": "params",
            "data": {},
        }
    lower = raw_src.lower()
    if "://" in raw_src or lower.startswith(("http:", "https:", "magnet:")):
        return {
            "ok": False,
            "message": "Only local files are allowed — no web or magnet links",
            "blocked_reason": "scheme",
            "data": {},
        }
    try:
        src = Path(raw_src).expanduser().resolve()
    except Exception:
        return {
            "ok": False,
            "message": "Invalid source path",
            "blocked_reason": "path",
            "data": {},
        }

    def under(path: Path) -> bool:
        for root in approved_roots:
            try:
                path.relative_to(root)
                return True
            except ValueError:
                continue
        return False

    if not under(src):
        return {
            "ok": False,
            "message": "Source file is outside approved folder roots",
            "blocked_reason": "allowlist",
            "data": {},
        }
    if src.suffix.lower() not in VIDEO_EXTS:
        return {
            "ok": False,
            "message": f"Unsupported media type: {src.suffix or '(none)'}",
            "blocked_reason": "filetype",
            "data": {},
        }
    if not src.is_file():
        return {
            "ok": False,
            "message": "Source is not a file",
            "blocked_reason": "path",
            "data": {},
        }
    mode_l = (mode or "copy").lower()
    if mode_l not in {"copy", "move"}:
        return {
            "ok": False,
            "message": "mode must be copy or move",
            "blocked_reason": "params",
            "data": {},
        }
    if not confirmed:
        return {
            "ok": False,
            "message": f"Confirm {mode_l} {src.name} into Plex library?",
            "blocked_reason": "confirm_required",
            "data": {"pending": True, "source": str(src), "mode": mode_l},
        }

    dest_dir = plex_library_dir.expanduser().resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if dest.exists() and not overwrite:
        return {
            "ok": False,
            "message": f"Already exists in library: {dest.name}",
            "blocked_reason": "exists",
            "data": {"dest": str(dest)},
        }

    copy_fn = copy_file_fn or (lambda a, b: shutil.copy2(a, b))
    move_fn = move_file_fn or (lambda a, b: shutil.move(str(a), str(b)))
    if mode_l == "copy":
        copy_fn(src, dest)
    else:
        move_fn(src, dest)

    scan_msg = None
    if scan_after:
        scan_res = request_plex_scan(scan_fn=scan_fn)
        scan_msg = scan_res["message"]
    msg = f"{'Moved' if mode_l == 'move' else 'Copied'} to Plex library: {dest.name}"
    if scan_msg:
        msg += f" ({scan_msg})"
    return {
        "ok": True,
        "message": msg,
        "blocked_reason": None,
        "data": {"source": str(src), "dest": str(dest), "mode": mode_l},
    }


def request_plex_scan(*, scan_fn: Callable[[], str] | None = None) -> dict[str, Any]:
    if scan_fn is None:
        return {
            "ok": True,
            "message": "File is in the library folder — open Plex and Scan Library when ready",
            "blocked_reason": None,
            "data": {},
        }
    try:
        detail = scan_fn()
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "message": f"Plex scan failed: {e}",
            "blocked_reason": "scan_error",
            "data": {},
        }
    return {
        "ok": True,
        "message": detail or "Plex scan requested",
        "blocked_reason": None,
        "data": {},
    }
