from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from assistant.actions.catalog import BLOCKED_ACTIONS, CATALOG, Risk


@dataclass
class ActionRequest:
    action: str
    params: dict[str, Any]
    confirmed: bool = False


@dataclass
class ActionResult:
    ok: bool
    action: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    blocked_reason: str | None = None


class ActionRouter:
    """Allowlisted PC actions. OS side effects are injectable for tests."""

    def __init__(
        self,
        *,
        allowlisted_apps: list[str],
        allowlisted_domains: list[str],
        folder_roots: list[Path],
        open_url_confirm_unknown_domain: bool = True,
        type_text_long_chars: int = 200,
        type_text_confirm_long: bool = True,
        open_app_fn: Callable[[str], None] | None = None,
        open_url_fn: Callable[[str], None] | None = None,
        type_text_fn: Callable[[str], None] | None = None,
        list_dir_fn: Callable[[Path], list[str]] | None = None,
        set_volume_fn: Callable[[int], None] | None = None,
        set_mute_fn: Callable[[bool], None] | None = None,
        audit_path: Path | None = None,
    ):
        self.apps = {a.lower() for a in allowlisted_apps}
        self.domains = {d.lower() for d in allowlisted_domains}
        self.roots = [r.expanduser().resolve() for r in folder_roots]
        self.open_url_confirm_unknown_domain = open_url_confirm_unknown_domain
        self.type_text_long_chars = type_text_long_chars
        self.type_text_confirm_long = type_text_confirm_long
        self._open_app = open_app_fn or (lambda app: None)
        self._open_url = open_url_fn or (lambda url: None)
        self._type_text = type_text_fn or (lambda text: None)
        self._list_dir = list_dir_fn or (lambda p: [x.name for x in p.iterdir()])
        self._set_volume = set_volume_fn or (lambda v: None)
        self._set_mute = set_mute_fn or (lambda m: None)
        self.audit_path = audit_path
        self.audit_log: list[dict[str, Any]] = []
        self._volume = 50
        self._muted = False

    def dispatch(self, req: ActionRequest) -> ActionResult:
        action = (req.action or "").strip()
        if action in BLOCKED_ACTIONS or action not in CATALOG:
            result = ActionResult(
                ok=False,
                action=action,
                message="Action rejected",
                blocked_reason="unknown_or_destructive",
            )
            self._audit(req, result)
            return result

        spec = CATALOG[action]
        handler = {
            "open_app": self._open_app_action,
            "open_url": self._open_url_action,
            "type_text": self._type_text_action,
            "list_files": self._list_files_action,
            "set_volume": self._set_volume_action,
            "set_mute": self._set_mute_action,
        }[action]
        result = handler(req)
        self._audit(req, result)
        return result

    def _needs_confirm(self, risk: Risk, already: bool, extra: bool = False) -> bool:
        if already:
            return False
        if risk == Risk.DESTRUCTIVE:
            return True
        if risk == Risk.MEDIUM or extra:
            return True
        return False

    def _open_app_action(self, req: ActionRequest) -> ActionResult:
        app = str(req.params.get("app", "")).strip().lower()
        if not app or app not in self.apps:
            return ActionResult(
                ok=False,
                action="open_app",
                message=f"App not allowlisted: {app or '(empty)'}",
                blocked_reason="allowlist",
            )
        self._open_app(app)
        return ActionResult(ok=True, action="open_app", message=f"Opened {app}", data={"app": app})

    def _open_url_action(self, req: ActionRequest) -> ActionResult:
        url = str(req.params.get("url", "")).strip()
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return ActionResult(
                ok=False,
                action="open_url",
                message="Only http(s) URLs are allowed",
                blocked_reason="scheme",
            )
        if parsed.scheme == "javascript" or url.lower().startswith("file:"):
            return ActionResult(
                ok=False,
                action="open_url",
                message="Blocked URL scheme",
                blocked_reason="scheme",
            )
        host = parsed.hostname.lower() if parsed.hostname else ""
        known = host in self.domains or any(host.endswith("." + d) for d in self.domains)
        needs = self.open_url_confirm_unknown_domain and not known
        if self._needs_confirm(Risk.MEDIUM, req.confirmed, extra=needs):
            return ActionResult(
                ok=False,
                action="open_url",
                message=f"Confirm open URL: {url}",
                blocked_reason="confirm_required",
                data={"pending": True, "url": url},
            )
        self._open_url(url)
        return ActionResult(ok=True, action="open_url", message=f"Opened {url}", data={"url": url})

    def _type_text_action(self, req: ActionRequest) -> ActionResult:
        text = str(req.params.get("text", ""))
        if re.search(r"(password|secret|api[_-]?key)", text, re.I):
            if not req.confirmed:
                return ActionResult(
                    ok=False,
                    action="type_text",
                    message="Confirm typing sensitive-looking text",
                    blocked_reason="confirm_required",
                    data={"pending": True},
                )
        if self.type_text_confirm_long and len(text) > self.type_text_long_chars and not req.confirmed:
            return ActionResult(
                ok=False,
                action="type_text",
                message="Confirm typing long text",
                blocked_reason="confirm_required",
                data={"pending": True},
            )
        # Never treat as shell
        self._type_text(text)
        return ActionResult(ok=True, action="type_text", message="Typed text", data={"chars": len(text)})

    def _list_files_action(self, req: ActionRequest) -> ActionResult:
        raw = str(req.params.get("path", "")).strip() or "."
        try:
            path = Path(raw).expanduser().resolve()
        except Exception:
            return ActionResult(
                ok=False,
                action="list_files",
                message="Invalid path",
                blocked_reason="path",
            )
        if not self._under_roots(path):
            return ActionResult(
                ok=False,
                action="list_files",
                message="Path outside approved roots",
                blocked_reason="allowlist",
            )
        try:
            entries = self._list_dir(path)
        except FileNotFoundError:
            return ActionResult(ok=False, action="list_files", message="Path not found")
        return ActionResult(
            ok=True,
            action="list_files",
            message=f"{len(entries)} entries: {", ".join(entries[:10])}",
            data={"path": str(path), "entries": entries},
        )

    def _set_volume_action(self, req: ActionRequest) -> ActionResult:
        try:
            level = int(req.params.get("level"))
        except (TypeError, ValueError):
            return ActionResult(ok=False, action="set_volume", message="Invalid volume")
        if level < 0 or level > 100:
            return ActionResult(ok=False, action="set_volume", message="Volume out of range")
        self._volume = level
        self._set_volume(level)
        return ActionResult(ok=True, action="set_volume", message=f"Volume {level}", data={"level": level})

    def _set_mute_action(self, req: ActionRequest) -> ActionResult:
        muted = bool(req.params.get("muted"))
        self._muted = muted
        self._set_mute(muted)
        return ActionResult(ok=True, action="set_mute", message=f"Muted={muted}", data={"muted": muted})

    def _under_roots(self, path: Path) -> bool:
        for root in self.roots:
            try:
                path.relative_to(root)
                return True
            except ValueError:
                continue
        return False

    def _audit(self, req: ActionRequest, result: ActionResult) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "action": req.action,
            "params": {k: v for k, v in req.params.items() if k != "text" or len(str(v)) < 80},
            "confirmed": req.confirmed,
            "ok": result.ok,
            "blocked_reason": result.blocked_reason,
            "message": result.message,
        }
        self.audit_log.append(entry)
        if self.audit_path:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            with self.audit_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
