from __future__ import annotations

import tempfile
from pathlib import Path

from assistant.actions.router import ActionRouter
from assistant.core.orchestrator import Orchestrator
from assistant.memory.store import MemoryStore
from assistant.voice.state_machine import VoiceState


def _orch(tmp: Path, roots: list[Path] | None = None) -> tuple[Orchestrator, list[str], list[str]]:
    opened_apps: list[str] = []
    opened_urls: list[str] = []
    root = roots or [tmp]
    for r in root:
        r.mkdir(parents=True, exist_ok=True)
    memory = MemoryStore(tmp / "memory.db")
    router = ActionRouter(
        allowlisted_apps=["notepad", "calculator", "calc"],
        allowlisted_domains=["example.com"],
        folder_roots=root,
        open_app_fn=opened_apps.append,
        open_url_fn=opened_urls.append,
        list_dir_fn=lambda p: sorted(x.name for x in p.iterdir()),
    )
    return Orchestrator(memory=memory, router=router), opened_apps, opened_urls


def run_scenarios() -> bool:
    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, ok, detail))
        print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" — {detail}" if detail else ""))

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        orch, apps, urls = _orch(tmp)

        # S1 teach + recall
        t1 = orch.handle_utterance("remember that my name is R.P.")
        t1b = orch.handle_utterance("yes")
        t1c = orch.handle_utterance("what is my name?")
        check("S1 teach+recall", t1b.memory_wrote and "R.P." in t1c.reply, t1c.reply)

        # S2 skill
        orch2, apps2, _ = _orch(tmp / "s2")
        orch2.handle_utterance("remember when I say morning, do open calculator")
        orch2.handle_utterance("yes")
        r = orch2.handle_utterance("morning")
        check("S2 skill invoke", r.action_ok is True and apps2 == ["calculator"], str(apps2))

        # S3 open allowlisted
        orch3, apps3, _ = _orch(tmp / "s3")
        r = orch3.handle_utterance("open calculator")
        check("S3 open app", r.action_ok is True and apps3 == ["calculator"])

        # S4 blocked URL scheme
        orch4, _, urls4 = _orch(tmp / "s4")
        r = orch4.handle_utterance("open file:///etc/passwd")
        # intent may classify oddly; force via open_url intent path
        from assistant.llm.intent import Intent

        r = orch4._run_intent(Intent("open_url", {"url": "file:///etc/passwd"}), confirmed=True)
        check("S4 block file URL", r.action_ok is False and not urls4)

        # S5 list files + traversal
        folder = tmp / "docs"
        folder.mkdir()
        (folder / "a.txt").write_text("x", encoding="utf-8")
        orch5, _, _ = _orch(tmp / "s5", roots=[folder])
        r = orch5.handle_utterance(f"list files in {folder}")
        ok_list = r.action_ok is True and ("a.txt" in str(r.reply) or "1 entries" in str(r.reply) or "1 entry" in str(r.reply) or r.reply.startswith("1"))
        r2 = orch5.handle_utterance(f"list files in {folder / '..' / '..'}")
        check("S5 list + block traversal", ok_list and r2.action_ok is False)

        # S6 volume mute
        orch6, _, _ = _orch(tmp / "s6")
        r = orch6.handle_utterance("volume 40")
        r2 = orch6.handle_utterance("mute")
        r3 = orch6.handle_utterance("unmute")
        r4 = orch6.handle_utterance("volume 200")
        check(
            "S6 volume/mute",
            r.action_ok and r2.action_ok and r3.action_ok and r4.action_ok is False,
        )

        # S7 confirm gate cancel
        orch7, _, urls7 = _orch(tmp / "s7")
        r = orch7.handle_utterance("open https://evil.example")
        pending = r.pending_confirm is not None
        orch7.handle_utterance("no")
        check("S7 confirm cancel", pending and urls7 == [])

        # S8 mic denied recovery path (state machine)
        v = orch.voice
        v.start_listen()
        v.mic_denied()
        check("S8 mic denied -> idle", v.state == VoiceState.IDLE and v.last_error)

        # S9 barge-in
        v.start_speak()
        v.barge_in()
        check("S9 barge-in -> listening", v.state == VoiceState.LISTENING)

        # S10 ambiguous no OS
        orch10, apps10, urls10 = _orch(tmp / "s10")
        r = orch10.handle_utterance("do something to my PC")
        check(
            "S10 ambiguous no action",
            r.action_ok is None and apps10 == [] and urls10 == [] and "What should I do" in (r.reply or ""),
        )

        # V9 late STT ignored
        v = orch.voice
        v.start_listen()
        gen = v.begin_stt()
        v.stt_hang_timeout()
        ignored = v.stt_result(gen, "open calculator")
        check("V9 late STT ignored", ignored is None)

        # Thinking ≠ listening visual
        orb = orch.orb
        orch.voice.start_listen()
        orch.voice.set_vu(0.8)
        listening = orch.orb.render()
        orch.voice.begin_stt()
        thinking = orch.orb.render()
        check(
            "UI thinking distinct",
            listening["shape"] == "ring-pulse"
            and thinking["shape"] == "orbit"
            and thinking["vu"] == 0.0,
        )

    passed = all(ok for _, ok, _ in results)
    print(f"\n{sum(1 for _, ok, _ in results if ok)}/{len(results)} passed")
    return passed


if __name__ == "__main__":
    raise SystemExit(0 if run_scenarios() else 1)
