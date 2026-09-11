from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from assistant.actions.router import ActionRouter
from assistant.config import expand_roots, load_config
from assistant.core.orchestrator import Orchestrator
from assistant.memory.store import MemoryStore
from assistant.scenarios import run_scenarios


def build_orchestrator(data_dir: Path) -> Orchestrator:
    cfg = load_config()
    allow = cfg.get("allowlist", {})
    perms = cfg.get("permissions", {})
    memory = MemoryStore(data_dir / "memory.db")
    router = ActionRouter(
        allowlisted_apps=list(allow.get("apps", [])),
        allowlisted_domains=list(allow.get("url_domains", [])),
        folder_roots=expand_roots(list(allow.get("folder_roots", ["~/Documents"]))),
        open_url_confirm_unknown_domain=bool(
            perms.get("open_url_confirm_unknown_domain", True)
        ),
        type_text_long_chars=int(perms.get("type_text_long_chars", 200)),
        type_text_confirm_long=bool(perms.get("type_text_confirm_long", True)),
        audit_path=data_dir / "audit.jsonl",
    )
    return Orchestrator(memory=memory, router=router)


def chat_loop() -> None:
    data = Path.home() / ".jarvis"
    data.mkdir(parents=True, exist_ok=True)
    orch = build_orchestrator(data)
    name = load_config().get("assistant_name", "Jarvis")
    print(f"{name} text console. Type 'quit' to exit. Teach with: remember that my name is …")
    print("Confirm pending actions with: yes / no")
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line.lower() in {"quit", "exit"}:
            break
        turn = orch.handle_utterance(line)
        print(turn.reply)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="jarvis")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("chat", help="Text REPL (same brain as voice)")
    sub.add_parser("scenarios", help="Run reliability scenario pack")
    args = parser.parse_args(argv)
    if args.cmd == "chat":
        chat_loop()
    elif args.cmd == "scenarios":
        raise SystemExit(0 if run_scenarios() else 1)


if __name__ == "__main__":
    main()
