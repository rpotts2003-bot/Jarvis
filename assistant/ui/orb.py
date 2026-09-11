from __future__ import annotations

from assistant.voice.state_machine import VoiceState


class ListeningOrb:
    """Headless HUD model for tests; GUI can bind to `render()` later."""

    LABELS = {
        VoiceState.IDLE: "Idle",
        VoiceState.LISTENING: "Listening",
        VoiceState.THINKING: "Thinking",
        VoiceState.SPEAKING: "Speaking",
        VoiceState.ERROR: "Error",
    }

    def __init__(self):
        self.state = VoiceState.IDLE
        self.vu = 0.0
        self.message = "Idle"

    def update(self, state: VoiceState, *, vu: float = 0.0, error: str | None = None) -> None:
        self.state = state
        # Thinking must not look like Listening: no VU
        self.vu = vu if state == VoiceState.LISTENING else 0.0
        base = self.LABELS[state]
        self.message = f"{base}" + (f" — {error}" if error else "")

    def render(self) -> dict:
        shape = {
            VoiceState.IDLE: "dot",
            VoiceState.LISTENING: "ring-pulse",
            VoiceState.THINKING: "orbit",
            VoiceState.SPEAKING: "ripple",
            VoiceState.ERROR: "mark",
        }[self.state]
        return {
            "label": self.message,
            "shape": shape,
            "vu": self.vu,
            "cancel_visible": self.state == VoiceState.SPEAKING,
        }
