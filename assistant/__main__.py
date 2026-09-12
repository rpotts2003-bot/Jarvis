from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from assistant.actions.router import ActionRouter
from assistant.envload import cloud_chat_enabled, load_env
from assistant.config import expand_roots, load_config, user_data_dir
from assistant.core.orchestrator import Orchestrator
from assistant.memory.store import MemoryStore
from assistant.scenarios import run_scenarios


def build_orchestrator(data_dir: Path) -> Orchestrator:
    load_env()
    cfg = load_config()
    allow = cfg.get("allowlist", {})
    perms = cfg.get("permissions", {})
    plex_cfg = cfg.get("plex", {})
    memory = MemoryStore(data_dir / "memory.db")
    plex_dir = plex_cfg.get("library_dir")
    router = ActionRouter(
        allowlisted_apps=list(allow.get("apps", [])),
        allowlisted_domains=list(allow.get("url_domains", [])),
        folder_roots=expand_roots(list(allow.get("folder_roots", ["~/Documents"]))),
        open_url_confirm_unknown_domain=bool(
            perms.get("open_url_confirm_unknown_domain", True)
        ),
        type_text_long_chars=int(perms.get("type_text_long_chars", 200)),
        type_text_confirm_long=bool(perms.get("type_text_confirm_long", True)),
        plex_library_dir=Path(plex_dir).expanduser() if plex_dir else None,
        audit_path=data_dir / "audit.jsonl",
    )
    return Orchestrator(memory=memory, router=router)


def chat_loop() -> None:
    data = user_data_dir()
    orch = build_orchestrator(data)
    name = load_config().get("assistant_name", "Jarvis")
    print(f"{name} — type what you want. Teach skills with:")
    print("  learn when I say morning, do open calculator")
    print("Then say: morning")
    print("Other: list skills | yes/no to confirm | quit")
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


def gui_loop() -> None:
    from assistant.ui.gui import run_gui
    from assistant.voice.adapters import MockTTS
    from assistant.voice.platform_io import make_mic_hear, make_tts
    from assistant.voice.wake import WakeConfig, WakeListener

    load_env()
    data = user_data_dir()
    orch = build_orchestrator(data)
    cfg = load_config()
    name = str(cfg.get("assistant_name", "Jarvis"))
    wake_name = os.environ.get("JARVIS_WAKE_NAME") or name
    always = os.environ.get("JARVIS_ALWAYS_LISTEN", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }

    # Single speak path: GUI owns talkback. Orchestrator TTS is a no-op so
    # _speak_result never double-speaks (pyttsx3 lock / silent second utter).
    tts = make_tts()
    orch.tts = MockTTS()

    def on_submit(text: str) -> str:
        turn = orch.handle_utterance(text)
        return turn.reply or ""

    status_bits = ["chat:OpenAI" if cloud_chat_enabled() else "chat:offline"]
    # Listen button: energy VAD (ptt). Wake loop: shorter fixed chunk.
    hear_ptt = make_mic_hear(mode="ptt")
    hear_wake = make_mic_hear(mode="wake")
    hear = hear_ptt
    status_bits.append("mic:on" if hear else "mic:type-only (install voice deps)")
    tts_label = getattr(tts, "status_label", None)
    if tts_label:
        status_bits.append(str(tts_label))

    wake = None
    if always:
        wake = WakeListener(
            config=WakeConfig(wake_name=str(wake_name)),
            hear=hear_wake or hear_ptt,
            hear_command=hear_ptt,
        )

        def _mic_err(msg: str) -> None:
            # Surfaced via wake on_state mic_denied + GUI caption path
            pass

        wake.on_error = _mic_err

    run_gui(
        title=name,
        on_submit=on_submit,
        wake=wake,
        status_hint=" · ".join(status_bits),
        speak=tts.speak,
        hear=hear,
    )



def _diagnose_report_paths() -> list[Path]:
    paths: list[Path] = []
    if getattr(sys, "frozen", False):
        paths.append(Path(sys.executable).resolve().parent / "jarvis_diagnose.txt")
    paths.append(user_data_dir() / "jarvis_diagnose.txt")
    paths.append(Path.cwd() / "jarvis_diagnose.txt")
    out: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key not in seen:
            seen.add(key)
            out.append(path)
    return out


def _run_diagnose() -> int:
    """Mic/TTS health check. Writes jarvis_diagnose.txt for windowed exe smoke."""
    from assistant.voice.mic_health import mark_probed, probe_microphone
    from assistant.voice.platform_io import make_tts

    load_env()
    lines: list[str] = []
    code = 0
    try:
        result = probe_microphone()
        mark_probed(status=result.status.value)
        lines.append(f"mic: {result.status.value}")
        lines.append(result.message)
        try:
            tts = make_tts()
            tts.speak("")
            label = getattr(tts, "status_label", None) or getattr(tts, "voice_name", None)
            lines.append(f"tts: ok ({label})" if label else "tts: ok")
        except Exception as e:
            lines.append(f"tts: fail ({e})")
            code = 1
        else:
            if result.status.value == "missing_dep":
                code = 2
            elif not result.ok:
                code = 3
    except Exception as e:
        lines.append(f"crash: {e}")
        code = 1

    lines.append(f"exit: {code}")
    text = "\n".join(lines) + "\n"
    for path in _diagnose_report_paths():
        try:
            path.write_text(text, encoding="utf-8")
        except Exception:
            pass
    try:
        print(text, end="")
    except Exception:
        pass
    return code



def main(argv: list[str] | None = None) -> None:
    # Double-click / no args → GUI window
    if argv is None and len(sys.argv) == 1:
        gui_loop()
        return
    parser = argparse.ArgumentParser(prog="jarvis")
    sub = parser.add_subparsers(dest="cmd", required=False)
    sub.add_parser("gui", help="Desktop window (chat + orb)")
    sub.add_parser("chat", help="Text-only console")
    sub.add_parser("scenarios", help="Run reliability scenario pack")
    sub.add_parser("diagnose", help="Mic/TTS health check (for smoke / exe)")
    args = parser.parse_args(argv)
    cmd = args.cmd or "gui"
    if cmd == "gui":
        gui_loop()
    elif cmd == "chat":
        chat_loop()
    elif cmd == "scenarios":
        raise SystemExit(0 if run_scenarios() else 1)
    elif cmd == "diagnose":
        raise SystemExit(_run_diagnose())


if __name__ == "__main__":
    main()
