from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class VoiceState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    ERROR = "error"


@dataclass
class VoiceMachine:
    silence_timeout_ms: int = 5000
    stt_hang_timeout_ms: int = 10000
    state: VoiceState = VoiceState.IDLE
    level: float = 0.0  # VU for listening only
    last_error: str | None = None
    _listen_gen: int = 0
    _speak_gen: int = 0
    _pending_stt_gen: int | None = None
    _on_change: Callable[[VoiceState], None] | None = None
    _tts_stop: Callable[[], None] | None = None

    def set_hooks(
        self,
        *,
        on_change: Callable[[VoiceState], None] | None = None,
        tts_stop: Callable[[], None] | None = None,
    ) -> None:
        self._on_change = on_change
        self._tts_stop = tts_stop

    def _set(self, state: VoiceState, *, level: float = 0.0, error: str | None = None) -> None:
        self.state = state
        self.level = level if state == VoiceState.LISTENING else 0.0
        self.last_error = error
        if self._on_change:
            self._on_change(state)

    def start_listen(self) -> VoiceState:
        if self.state == VoiceState.SPEAKING:
            self.cancel_speak()
        self._listen_gen += 1
        self._set(VoiceState.LISTENING, level=0.1)
        return self.state

    def set_vu(self, level: float) -> None:
        if self.state == VoiceState.LISTENING:
            self.level = max(0.0, min(1.0, level))
            if self._on_change:
                self._on_change(self.state)

    def mic_denied(self) -> VoiceState:
        self._set(VoiceState.ERROR, error="microphone denied")
        self._set(VoiceState.IDLE, error="microphone denied")
        return self.state

    def mic_disconnected(self) -> VoiceState:
        self._set(VoiceState.ERROR, error="mic disconnected")
        self._set(VoiceState.IDLE, error="mic disconnected")
        return self.state

    def silence_timeout(self) -> VoiceState:
        if self.state == VoiceState.LISTENING:
            self._set(VoiceState.IDLE, error="silence timeout")
        return self.state

    def begin_stt(self) -> int:
        """Transition listening -> thinking; returns generation for hang protection."""
        gen = self._listen_gen
        self._pending_stt_gen = gen
        if self.state == VoiceState.LISTENING:
            self._set(VoiceState.THINKING)
        return gen

    def stt_result(self, gen: int, transcript: str | None) -> str | None:
        """Accept STT only if generation matches; late results ignored."""
        if self._pending_stt_gen is None or gen != self._pending_stt_gen:
            return None  # late / cancelled
        self._pending_stt_gen = None
        return transcript

    def stt_hang_timeout(self) -> VoiceState:
        self._pending_stt_gen = None
        self._set(VoiceState.ERROR, error="stt timeout")
        self._set(VoiceState.IDLE, error="stt timeout")
        return self.state

    def model_missing(self) -> VoiceState:
        self._set(VoiceState.ERROR, error="voice offline / model missing")
        self._set(VoiceState.IDLE, error="voice offline / model missing")
        return self.state

    def start_speak(self) -> VoiceState:
        self._speak_gen += 1
        self._set(VoiceState.SPEAKING)
        return self.state

    def cancel_speak(self) -> VoiceState:
        if self._tts_stop:
            self._tts_stop()
        self._speak_gen += 1
        if self.state == VoiceState.SPEAKING:
            self._set(VoiceState.IDLE)
        return self.state

    def barge_in(self) -> VoiceState:
        """Stop TTS and enter listening."""
        if self._tts_stop:
            self._tts_stop()
        self._speak_gen += 1
        self._listen_gen += 1
        self._set(VoiceState.LISTENING, level=0.1)
        return self.state

    def finish_speak(self) -> VoiceState:
        if self.state == VoiceState.SPEAKING:
            self._set(VoiceState.IDLE)
        return self.state

    def cancel(self) -> VoiceState:
        self._pending_stt_gen = None
        if self.state == VoiceState.SPEAKING:
            return self.cancel_speak()
        self._set(VoiceState.IDLE)
        return self.state

    def snapshot(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "level": self.level,
            "error": self.last_error,
            "is_listening_visual": self.state == VoiceState.LISTENING,
            "is_thinking_visual": self.state == VoiceState.THINKING,
        }
