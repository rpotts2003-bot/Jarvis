from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from assistant.actions.router import ActionRequest, ActionRouter
from assistant.llm.builtins import chat_reply, try_builtin
from assistant.skills.runner import try_registry_skill
from assistant.llm.intent import Intent, parse_intent
from assistant.memory.store import MemoryStore
from assistant.ui.orb import ListeningOrb
from assistant.voice.adapters import MockTTS, STTAdapter, TTSAdapter
from assistant.voice.state_machine import VoiceMachine, VoiceState


@dataclass
class TurnResult:
    reply: str
    intent: Intent
    action_ok: bool | None = None
    pending_confirm: dict[str, Any] | None = None
    memory_wrote: bool = False
    state: str = "idle"


class Orchestrator:
    def __init__(
        self,
        memory: MemoryStore,
        router: ActionRouter,
        voice: VoiceMachine | None = None,
        orb: ListeningOrb | None = None,
        tts: TTSAdapter | None = None,
        stt: STTAdapter | None = None,
    ):
        self.memory = memory
        self.router = router
        self.voice = voice or VoiceMachine()
        self.orb = orb or ListeningOrb()
        self.tts = tts or MockTTS()
        self.stt = stt
        self.pending: dict[str, Any] | None = None
        self._history: list[tuple[str, str]] = []
        self.voice.set_hooks(
            on_change=lambda s: self.orb.update(
                s, vu=self.voice.level, error=self.voice.last_error
            ),
            tts_stop=self.tts.stop,
        )

    def handle_text(self, text: str, *, confirmed: bool = False) -> TurnResult:
        # confirmation of pending teach/action
        low = text.strip().lower()
        if self.pending and low in {"yes", "y", "confirm", "ok"}:
            return self._flush_pending(confirm=True)
        if self.pending and low in {"no", "n", "cancel"}:
            self.pending = None
            return TurnResult(reply="Cancelled.", intent=Intent_clarify())

        intent = parse_intent(text)
        return self._run_intent(intent, confirmed=confirmed)

    def _run_intent(self, intent: Intent, *, confirmed: bool) -> TurnResult:
        if intent.kind == "clarify":
            return self._speak_result(
                TurnResult(reply=intent.reply or "Please clarify.", intent=intent)
            )
        if intent.kind == "chat":
            text = intent.params.get("text") or intent.reply or ""
            reply = chat_reply(text, history=getattr(self, "_history", None))
            self._remember_turn("user", text)
            self._remember_turn("assistant", reply)
            return self._speak_result(TurnResult(reply=reply, intent=intent))
        if intent.kind == "teach":
            if not confirmed:
                self.pending = {"type": "teach", "intent": intent}
                return TurnResult(
                    reply=(
                    f'Got it — learn "{intent.params.get("key")}" → {intent.params.get("value")}? '
                    if intent.params.get("tier") == "skill"
                    else f"Remember {intent.params.get('key')} = {intent.params.get('value')}? "
                )
                + "Say yes to save.",
                    intent=intent,
                    pending_confirm=dict(intent.params),
                )
            item = self.memory.write(
                intent.params["tier"],
                intent.params["key"],
                intent.params["value"],
                confirmed=True,
            )
            return self._speak_result(
                TurnResult(
                    reply="Got it — saved." if item else "Not saved.",
                    intent=intent,
                    memory_wrote=item is not None,
                )
            )
        if intent.kind == "list_skills":
            skills = self.memory.list_tier("skill")
            if not skills:
                reply = "No skills saved yet. Teach me with: learn when I say morning, do open calculator"
            else:
                lines = [f'- say "{s.key}" → {s.value}' for s in skills]
                reply = "Skills I know:\n" + "\n".join(lines)
            return self._speak_result(TurnResult(reply=reply, intent=intent))

        if intent.kind == "forget":
            if not confirmed:
                self.pending = {"type": "forget", "intent": intent}
                return TurnResult(
                    reply=f"Forget {intent.params.get('key')}? Say yes to confirm.",
                    intent=intent,
                    pending_confirm=dict(intent.params),
                )
            ok = self.memory.forget(
                intent.params["tier"], intent.params["key"], confirmed=True
            )
            return self._speak_result(
                TurnResult(reply="Forgotten." if ok else "Nothing to forget.", intent=intent)
            )
        if intent.kind == "recall":
            query = intent.params.get("query", "")
            val = self.memory.recall_text(query)
            # also try exact profile key
            if val is None:
                item = self.memory.get("profile", str(query).lower())
                val = item.value if item else None
            if val:
                return self._speak_result(TurnResult(reply=val, intent=intent))
            # Miss: free-form chat (bundled GGUF), not a dead-end "not saved" string
            text = (intent.params.get("text") or query or "").strip()
            reply = chat_reply(text, history=getattr(self, "_history", None))
            self._remember_turn("user", text)
            self._remember_turn("assistant", reply)
            return self._speak_result(TurnResult(reply=reply, intent=intent))

        # skills: if user utterance matches skill key, run value as nested command
        skill = self.memory.get("skill", intent.params.get("app", "")) if intent.kind == "open_app" else None
        # general skill trigger: exact chat match against skill keys
        # handled below for open_* etc.

        action_map = {
            "open_app": "open_app",
            "open_url": "open_url",
            "list_files": "list_files",
            "set_volume": "set_volume",
            "set_mute": "set_mute",
            "type_text": "type_text",
            "add_to_plex": "add_to_plex",
            "plex_scan": "plex_scan",
        }
        if intent.kind in action_map:
            # skill invocation: "open X" not used; check if raw skill exists for clarify path
            req = ActionRequest(
                action=action_map[intent.kind], params=intent.params, confirmed=confirmed
            )
            result = self.router.dispatch(req)
            if result.blocked_reason == "confirm_required":
                self.pending = {
                    "type": "action",
                    "request": req,
                    "intent": intent,
                }
                return TurnResult(
                    reply=result.message,
                    intent=intent,
                    action_ok=False,
                    pending_confirm=result.data,
                )
            reply = result.message if result.ok else f"Blocked: {result.message}"
            return self._speak_result(
                TurnResult(reply=reply, intent=intent, action_ok=result.ok)
            )

        return self._speak_result(
            TurnResult(reply="I’m not sure what to do with that.", intent=intent)
        )

    def try_skill(self, utterance: str, *, confirmed: bool = False) -> TurnResult | None:
        key = utterance.strip().lower()
        skill = self.memory.get("skill", key)
        if not skill:
            return None
        # skill value is a command string
        return self.handle_text(skill.value, confirmed=confirmed)

    def handle_utterance(self, text: str, *, confirmed: bool = False) -> TurnResult:
        # Built-in skill registry (Agent Brain pack) before taught skills / chat
        reg = try_registry_skill(self, text, confirmed=confirmed)
        if reg is not None:
            return reg

        skill_turn = self.try_skill(text, confirmed=confirmed)
        if skill_turn:
            return skill_turn

        builtin = try_builtin(text)
        if builtin is not None:
            self._remember_turn("user", text)
            self._remember_turn("assistant", builtin)
            return self._speak_result(
                TurnResult(reply=builtin, intent=Intent("chat", reply=builtin))
            )
        return self.handle_text(text, confirmed=confirmed)

    def _remember_turn(self, role: str, content: str) -> None:
        if not hasattr(self, "_history") or self._history is None:
            self._history: list[tuple[str, str]] = []
        self._history.append((role, content))
        self._history = self._history[-12:]

    def _flush_pending(self, *, confirm: bool) -> TurnResult:
        pending = self.pending
        self.pending = None
        if not pending or not confirm:
            return TurnResult(reply="Cancelled.", intent=Intent_clarify())
        if pending["type"] == "teach":
            return self._run_intent(pending["intent"], confirmed=True)
        if pending["type"] == "forget":
            return self._run_intent(pending["intent"], confirmed=True)
        if pending["type"] == "action":
            req: ActionRequest = pending["request"]
            req.confirmed = True
            result = self.router.dispatch(req)
            reply = result.message if result.ok else f"Blocked: {result.message}"
            return self._speak_result(
                TurnResult(reply=reply, intent=pending["intent"], action_ok=result.ok)
            )
        return TurnResult(reply="Nothing pending.", intent=Intent_clarify())

    def _speak_result(self, turn: TurnResult) -> TurnResult:
        self.voice.start_speak()
        self.tts.speak(turn.reply)
        self.voice.finish_speak()
        turn.state = self.voice.state.value
        return turn

    def ptt_begin(self) -> None:
        self.voice.start_listen()

    def ptt_end_with_transcript(self, transcript: str) -> TurnResult:
        gen = self.voice.begin_stt()
        accepted = self.voice.stt_result(gen, transcript)
        if accepted is None:
            return TurnResult(
                reply="Ignored late transcript.",
                intent=Intent_clarify(),
                state=self.voice.state.value,
            )
        return self.handle_utterance(accepted)


def Intent_clarify():
    from assistant.llm.intent import Intent

    return Intent("clarify")
