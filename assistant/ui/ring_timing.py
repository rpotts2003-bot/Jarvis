"""Voice UI critical ring timing — headless model the HUD and tests share."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

from assistant.voice.state_machine import VoiceState

# Spec constants (Voice UI)
LISTEN_BRIGHTEN_MS = 120.0
LISTEN_FIRST_PULSE_MS = 150.0
IDLE_LISTEN_CYCLE_S = 1.4  # mid of 1.2–1.6
VU_SMOOTH_MS = 60.0  # mid of 40–80
VU_KILL_MS = 100.0
CROSSFADE_MS = 200.0  # mid of 150–250
BARGE_IN_MS = 0.0  # hard cut
NOISE_FLOOR = 0.05


def _now() -> float:
    return time.monotonic()


@dataclass
class RingTiming:
    """Computes brightness / radius / opacity drivers per Voice UI timing."""

    reduced_motion: bool = False
    state: VoiceState = VoiceState.IDLE
    _entered_at: float = field(default_factory=_now)
    _prev_state: VoiceState = VoiceState.IDLE
    _raw_level: float = 0.0  # mic VU or TTS envelope 0..1
    _smooth: float = 0.0
    _last_tick: float = field(default_factory=_now)
    _vu_kill_until: float = 0.0
    _hard_cut: bool = False

    def set_state(self, state: VoiceState, *, barge_in: bool = False) -> None:
        if state == self.state and not barge_in:
            return
        self._prev_state = self.state
        self._hard_cut = barge_in or (
            self.state == VoiceState.SPEAKING
            and state in {VoiceState.LISTENING, VoiceState.IDLE}
        )
        # Listening → Thinking: schedule VU kill window
        if self.state == VoiceState.LISTENING and state == VoiceState.THINKING:
            self._vu_kill_until = _now() + VU_KILL_MS / 1000.0
            self._raw_level = 0.0
        self.state = state
        self._entered_at = _now()
        if self._hard_cut:
            self._smooth = 0.0 if state != VoiceState.LISTENING else max(self._smooth, 0.15)

    def set_level(self, level: float) -> None:
        """Mic VU (listening) or TTS envelope (speaking). Ignored in Thinking after kill."""
        self._raw_level = max(0.0, min(1.0, level))

    def tick(self, now: float | None = None) -> dict[str, float | str | bool]:
        now = now if now is not None else _now()
        dt = max(0.0, now - self._last_tick)
        self._last_tick = now
        since = (now - self._entered_at) * 1000.0  # ms

        # Smooth VU / envelope toward target (or 0 during kill / thinking)
        target = self._target_level(now)
        alpha = 1.0 - math.exp(-dt / (VU_SMOOTH_MS / 1000.0)) if VU_SMOOTH_MS > 0 else 1.0
        self._smooth += (target - self._smooth) * alpha

        if self.reduced_motion:
            return {
                "brightness": 1.0 if self.state != VoiceState.IDLE else 0.55,
                "pulse": 1.0,
                "radius_mul": 1.0,
                "opacity": 1.0,
                "rot_speed": 0.0,
                "shimmer": 0.0,
                "crossfade": 1.0,
                "label": self.state.value,
                "reduced_motion": True,
            }

        brightness = self._brightness(since)
        pulse, radius_mul, shimmer = self._motion(now, since)
        crossfade = 1.0 if self._hard_cut else min(1.0, since / CROSSFADE_MS)

        return {
            "brightness": brightness,
            "pulse": pulse,
            "radius_mul": radius_mul,
            "opacity": 0.55 + 0.45 * brightness,
            "rot_speed": self._rot_speed(),
            "shimmer": shimmer,
            "crossfade": crossfade,
            "level_smooth": self._smooth,
            "label": self.state.value,
            "reduced_motion": False,
        }

    def _target_level(self, now: float) -> float:
        if self.state == VoiceState.THINKING:
            return 0.0
        if self.state == VoiceState.LISTENING and now < self._vu_kill_until:
            return 0.0
        if self.state not in {VoiceState.LISTENING, VoiceState.SPEAKING}:
            return 0.0
        return self._raw_level

    def _brightness(self, since_ms: float) -> float:
        if self.state == VoiceState.LISTENING:
            # brighten within 120 ms of enter
            return min(1.0, 0.55 + 0.45 * min(1.0, since_ms / LISTEN_BRIGHTEN_MS))
        if self.state == VoiceState.SPEAKING:
            return 0.85 + 0.15 * self._smooth
        if self.state == VoiceState.THINKING:
            return 0.75
        if self.state == VoiceState.ERROR:
            return 0.9
        return 0.55

    def _motion(self, now: float, since_ms: float) -> tuple[float, float, float]:
        """Returns pulse (0..~1.1), radius_mul, shimmer."""
        if self.state == VoiceState.LISTENING:
            # First amplitude pulse by ~150 ms so it never feels dead
            intro = min(1.0, since_ms / LISTEN_FIRST_PULSE_MS)
            if self._raw_level > NOISE_FLOOR:
                # track VU
                radius = 1.0 + 0.12 * self._smooth
                pulse = 0.85 + 0.15 * self._smooth
                return pulse * intro + (1 - intro) * 0.7, radius, 0.0
            # idle-listen cycle 1.2–1.6 s
            phase = (now - self._entered_at) / IDLE_LISTEN_CYCLE_S
            wave = 0.5 + 0.5 * math.sin(phase * 2 * math.pi)
            pulse = 0.92 + 0.08 * wave
            radius = 1.0 + 0.05 * wave
            # ensure first pulse peaks near 150ms
            if since_ms < LISTEN_FIRST_PULSE_MS:
                kick = math.sin((since_ms / LISTEN_FIRST_PULSE_MS) * math.pi)
                pulse = max(pulse, 0.9 + 0.1 * kick)
                radius = max(radius, 1.0 + 0.06 * kick)
            return pulse, radius, 0.0

        if self.state == VoiceState.THINKING:
            # steady non-reactive shimmer — not listen pulse
            shimmer = 0.5 + 0.5 * math.sin(now * 2.2)
            return 1.0, 1.0, shimmer

        if self.state == VoiceState.SPEAKING:
            # TTS envelope driven
            pulse = 0.9 + 0.12 * self._smooth
            radius = 1.0 + 0.14 * self._smooth
            return pulse, radius, 0.0

        if self.state == VoiceState.ERROR:
            return 1.0, 1.0, 0.3

        # idle
        return 1.0, 1.0, 0.0

    def _rot_speed(self) -> float:
        return {
            VoiceState.IDLE: 8.0,
            VoiceState.LISTENING: 70.0,
            VoiceState.THINKING: 28.0,
            VoiceState.SPEAKING: 90.0,
            VoiceState.ERROR: 12.0,
        }.get(self.state, 8.0)
