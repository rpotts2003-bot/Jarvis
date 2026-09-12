"""Always-on wake pipeline per Voice UI constraints (headless + testable)."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

from assistant.config import user_data_dir

_log = logging.getLogger("jarvis.wake")

# Phonetic / STT variants Google often returns instead of "Jarvis"
_DEFAULT_WAKE_VARIANTS = (
    "jarvis",
    "jervis",
    "jarves",
    "jarvies",
    "jarvis's",
    "jarvis'",
    "jarvice",
    "jarvis,",
    "jarvus",
    "jarvish",
    "jarviz",
    "gervis",
)

_WAKE_PREFIXES = ("hey", "ok", "okay")


class WakePhase(str, Enum):
    IDLE_ARMED = "idle_armed"  # wake detector only; dim rings, no VU
    LISTENING = "listening"  # command window after wake
    BUSY = "busy"  # thinking/speaking — debounce wakes unless barge-in
    MUTED = "muted"


@dataclass
class WakeConfig:
    wake_name: str = "Jarvis"
    # VAD / timeouts (seconds)
    preroll_s: float = 0.4  # 300–500 ms
    end_silence_s: float = 0.8  # 700–900 ms
    no_speech_timeout_s: float = 10.0  # post-wake wait for first speech (~10–12 s)
    max_utterance_s: float = 18.0  # 15–20 s
    min_speech_s: float = 0.15  # ignore spikes <~150 ms
    energy_floor: float = 0.08  # adaptive baseline offset
    wake_confidence_min: float = 0.72
    wake_debounce_s: float = 1.2  # 1.0–1.5 s
    poll_s: float = 0.05
    # Post-wake command capture window (Windows SR / Google Listen path)
    followup_window_s: float = 12.0


@dataclass
class WakePipeline:
    """Pure logic for wake → command window → idle. No audio I/O."""

    config: WakeConfig = field(default_factory=WakeConfig)
    phase: WakePhase = WakePhase.IDLE_ARMED
    muted: bool = False
    last_wake_at: float = 0.0
    speech_started_at: float | None = None
    last_voice_at: float | None = None
    listen_opened_at: float | None = None
    energy_ema: float = 0.02
    abandoned_wakes: int = 0
    false_wakes: int = 0
    _speech_accum_s: float = 0.0

    def _variants(self) -> tuple[str, ...]:
        primary = (self.config.wake_name or "Jarvis").strip().lower()
        primary = re.sub(r"[,.:;!'\"]+$", "", primary)
        base = list(_DEFAULT_WAKE_VARIANTS)
        if primary and primary not in base:
            base.insert(0, primary)
            if not primary.endswith("s"):
                base.append(primary + "'s")
        seen: set[str] = set()
        out: list[str] = []
        for v in base:
            key = v.lower().rstrip(",.:;!")
            if key and key not in seen:
                seen.add(key)
                out.append(key)
        return tuple(out)

    def _norm_token(self, word: str) -> str:
        w = (word or "").lower().strip()
        w = w.strip(",.:;!")
        if w.endswith("'s"):
            w = w[:-2]
        return w

    def _is_wake_token(self, word: str) -> bool:
        core = self._norm_token(word)
        if not core:
            return False
        variants = self._variants()
        if core in variants:
            return True
        # Near-miss STT (jarves/jervis already listed; allow tiny edit distance)
        for v in variants:
            if abs(len(core) - len(v)) <= 2 and len(core) >= 4:
                # share prefix of 3+ chars
                if core[:3] == v[:3]:
                    # Hamming-ish: count differing chars on aligned prefix
                    n = min(len(core), len(v))
                    diff = sum(1 for i in range(n) if core[i] != v[i]) + abs(len(core) - len(v))
                    if diff <= 2:
                        return True
        return False

    def _wake_token_re(self) -> re.Pattern[str]:
        parts = sorted({re.escape(v) for v in self._variants()}, key=len, reverse=True)
        alt = "|".join(parts)
        return re.compile(rf"\b(?:{alt})\b", re.I)

    def _wake_re(self) -> re.Pattern[str]:
        token = self._wake_token_re().pattern
        return re.compile(rf"(?:(?:hey|ok|okay)\s+)?(?:{token})", re.I)

    def _tokenize(self, text: str) -> list[str]:
        t = re.sub(r"^[\s,.:;!\-]+", "", (text or "").strip())
        if not t:
            return []
        return re.findall(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?", t)

    def strip_wake(self, text: str) -> str:
        t = (text or "").strip()
        # Prefer structured strip using token positions so variants always drop
        words = self._tokenize(t)
        if words:
            window = words[:4]
            wake_idx = None
            for i, w in enumerate(window):
                if self._is_wake_token(w):
                    # preceding must be prefixes
                    if all(self._norm_token(x) in _WAKE_PREFIXES for x in window[:i]):
                        wake_idx = i
                        break
            if wake_idx is not None:
                # Rebuild leftover from original by removing prefix+wake via regex once
                t = self._wake_re().sub("", t, count=1)
                return re.sub(r"^[\s,.:;!\-]+", "", t).strip()
        t = self._wake_re().sub("", t, count=1)
        return re.sub(r"^[\s,.:;!\-]+", "", t).strip()

    def wake_at_start(self, text: str) -> bool:
        """True if a Jarvis variant leads (optional hey/ok), within the first ~4 words.

        Voice UI: do not open Listening on VAD alone or mid-sentence name drops.
        Preceding words before the wake token may only be hey/ok/okay.
        """
        words = self._tokenize(text)
        if not words:
            return False
        window = words[:4]
        for i, w in enumerate(window):
            if not self._is_wake_token(w):
                continue
            # Words before wake must be prefixes only (reject "please Jarvis …")
            if all(self._norm_token(x) in _WAKE_PREFIXES for x in window[:i]):
                return True
            return False
        return False

    def is_wake_only_or_wake_plus_command(self, text: str) -> bool:
        """Accept wake-gated STT if name leads; leftover may be the command."""
        return self.wake_at_start(text)

    def set_muted(self, muted: bool) -> WakePhase:
        self.muted = muted
        if muted:
            self.phase = WakePhase.MUTED
            self._reset_listen()
        else:
            self.phase = WakePhase.IDLE_ARMED
        return self.phase

    def set_busy(self, busy: bool) -> WakePhase:
        if self.muted:
            return WakePhase.MUTED
        self.phase = WakePhase.BUSY if busy else WakePhase.IDLE_ARMED
        if not busy:
            self._reset_listen()
        return self.phase

    def _reset_listen(self) -> None:
        self.speech_started_at = None
        self.last_voice_at = None
        self.listen_opened_at = None
        self._speech_accum_s = 0.0

    def try_wake(
        self,
        text: str,
        *,
        confidence: float = 1.0,
        now: float | None = None,
        barge_in: bool = False,
    ) -> bool:
        """Accept a wake hypothesis. Returns True if Listening opens."""
        now = time.monotonic() if now is None else now
        if self.muted:
            _log.info("wake ignored: muted (unmute tip)")
            return False
        if confidence < self.config.wake_confidence_min:
            self.false_wakes += 1
            _log.info("false-wake: low confidence=%.2f text=%r", confidence, text)
            return False
        if not text or not self.wake_at_start(text):
            self.false_wakes += 1
            _log.info("false-wake: no start match text=%r", text)
            return False
        if self.phase == WakePhase.BUSY and not barge_in:
            _log.info("wake ignored: busy (no barge-in) text=%r", text)
            return False
        if now - self.last_wake_at < self.config.wake_debounce_s:
            _log.info("wake ignored: debounce text=%r", text)
            return False
        self.last_wake_at = now
        self.phase = WakePhase.LISTENING
        self.listen_opened_at = now
        self.speech_started_at = None
        self.last_voice_at = None
        self._speech_accum_s = 0.0
        _log.info("wake accepted text=%r leftover=%r", text, self.strip_wake(text))
        return True

    def feed_energy(self, level: float, dt: float, *, now: float | None = None) -> str | None:
        """During LISTENING, feed VU 0..1. Returns event: None|'thinking'|'idle_timeout'|'idle_max'."""
        now = time.monotonic() if now is None else now
        if self.phase != WakePhase.LISTENING or self.muted:
            return None
        assert self.listen_opened_at is not None

        # Adaptive floor
        self.energy_ema = 0.95 * self.energy_ema + 0.05 * max(0.0, level)
        floor = self.energy_ema + self.config.energy_floor
        voiced = level > floor

        if voiced:
            self._speech_accum_s += dt
            if self._speech_accum_s >= self.config.min_speech_s:
                if self.speech_started_at is None:
                    self.speech_started_at = now
                self.last_voice_at = now
        else:
            self._speech_accum_s = 0.0

        # No speech after wake
        if self.speech_started_at is None:
            if now - self.listen_opened_at >= self.config.no_speech_timeout_s:
                self.abandoned_wakes += 1
                self.phase = WakePhase.IDLE_ARMED
                self._reset_listen()
                return "idle_timeout"
            return None

        # Max utterance
        if now - self.speech_started_at >= self.config.max_utterance_s:
            self.phase = WakePhase.BUSY
            return "thinking"

        # End of speech silence
        if self.last_voice_at and now - self.last_voice_at >= self.config.end_silence_s:
            self.phase = WakePhase.BUSY
            return "thinking"

        return None

    def cancel_to_idle(self) -> None:
        self.phase = WakePhase.MUTED if self.muted else WakePhase.IDLE_ARMED
        self._reset_listen()


@dataclass
class WakeListener:
    """Runtime wrapper: pipeline + optional hear() thread."""

    config: WakeConfig = field(default_factory=WakeConfig)
    pipeline: WakePipeline = field(init=False)
    muted: bool = False
    running: bool = False
    on_command: Callable[[str], None] | None = None
    on_state: Callable[[str], None] | None = None
    on_error: Callable[[str], None] | None = None
    capturing: bool = True  # app-level: when False, discard frames / don't call hear
    _thread: threading.Thread | None = None
    _stop: threading.Event = field(default_factory=threading.Event)
    hear: Callable[[], str | None] | None = None
    # Optional: hear_command() used after wake for full STT (can be heavier)
    hear_command: Callable[[], str | None] | None = None

    def __post_init__(self) -> None:
        self.pipeline = WakePipeline(config=self.config)
        self.pipeline.muted = self.muted
        if self.muted:
            self.pipeline.phase = WakePhase.MUTED

    def _emit(self, state: str) -> None:
        if self.on_state:
            self.on_state(state)

    def strip_wake(self, text: str) -> str:
        return self.pipeline.strip_wake(text)

    def set_muted(self, muted: bool) -> None:
        self.muted = muted
        self.capturing = not muted
        self.pipeline.set_muted(muted)
        self._persist_mute(muted)
        self._emit("muted" if muted else "idle_armed")

    def toggle_mute(self) -> bool:
        self.set_muted(not self.muted)
        return self.muted

    def set_busy(self, busy: bool) -> None:
        self.pipeline.set_busy(busy)
        if not self.muted:
            self._emit("busy" if busy else "idle_armed")

    def handle_transcript(self, text: str, *, confidence: float = 1.0) -> str | None:
        """Process a wake-candidate phrase (unit-test / simple backends)."""
        if self.muted or not self.capturing:
            if self.muted:
                self._emit("muted")
            return None
        if not self.pipeline.try_wake(text, confidence=confidence):
            return None
        self._emit("wake")
        cmd = self.pipeline.strip_wake(text)
        # Tiny leftover (STT noise / trailing comma) → treat as bare wake
        if cmd and len(cmd.split()) <= 1 and len(cmd) <= 2 and not cmd.isalnum():
            cmd = ""
        if cmd:
            self.pipeline.set_busy(True)
            self._emit("busy")
            return cmd
        # Bare wake — open command window with clear HUD, then one follow-up capture
        self._emit("listening")
        hear_cmd = self.hear_command or self.hear
        if hear_cmd:
            # Prefer longer no-speech wait / Recognize window on post-wake hear
            prev_wait = getattr(hear_cmd, "wait_speech_s", None)
            prev_timeout = getattr(hear_cmd, "timeout_s", None)
            target_win = max(
                float(self.config.no_speech_timeout_s),
                float(self.config.followup_window_s),
                10.0,
            )
            try:
                if hasattr(hear_cmd, "wait_speech_s"):
                    hear_cmd.wait_speech_s = max(  # type: ignore[attr-defined]
                        float(getattr(hear_cmd, "wait_speech_s", 0) or 0),
                        target_win,
                    )
                # Windows SR path: ensure Recognize timeout is ~10–15s for the command
                if hasattr(hear_cmd, "timeout_s"):
                    hear_cmd.timeout_s = max(  # type: ignore[attr-defined]
                        float(getattr(hear_cmd, "timeout_s", 0) or 0),
                        min(15.0, target_win if target_win >= 10.0 else 12.0),
                        12.0,
                    )
                # Brief grace so user can start speaking after hearing the wake chime/HUD
                time.sleep(0.35)
                follow = (hear_cmd() or "").strip()
            finally:
                if prev_wait is not None and hasattr(hear_cmd, "wait_speech_s"):
                    hear_cmd.wait_speech_s = prev_wait  # type: ignore[attr-defined]
                if prev_timeout is not None and hasattr(hear_cmd, "timeout_s"):
                    hear_cmd.timeout_s = prev_timeout  # type: ignore[attr-defined]
            if follow:
                if self.pipeline.wake_at_start(follow):
                    follow = self.pipeline.strip_wake(follow)
                self.pipeline.set_busy(True)
                self._emit("busy")
                return follow or None
            self.pipeline.abandoned_wakes += 1
            self.pipeline.cancel_to_idle()
            self._emit("idle_timeout")
            return None
        self.pipeline.abandoned_wakes += 1
        self.pipeline.cancel_to_idle()
        self._emit("idle_timeout")
        return None

    def start(self) -> None:
        if self.running:
            return
        saved = _load_mute_pref()
        if saved is not None:
            self.set_muted(saved)
        self.running = True
        self._stop.clear()
        self._emit("muted" if self.muted else "idle_armed")
        if self.hear is None:
            return

        def loop() -> None:
            while not self._stop.is_set():
                if self.muted or not self.capturing:
                    time.sleep(self.config.poll_s)
                    continue
                if self.pipeline.phase == WakePhase.BUSY:
                    time.sleep(self.config.poll_s)
                    continue
                try:
                    # Wake-only path: short/cheap hear — not continuous full Whisper
                    heard = self.hear() if self.hear else None
                except PermissionError as e:
                    if self.on_error:
                        self.on_error(f"microphone denied: {e}")
                    self._emit("mic_denied")
                    time.sleep(2.0)
                    continue
                except OSError as e:
                    # Often OS mute / device missing
                    if self.on_error:
                        self.on_error(f"microphone unavailable: {e}")
                    self._emit("mic_denied")
                    time.sleep(2.0)
                    continue
                except Exception:
                    time.sleep(0.5)
                    continue
                if not heard:
                    continue
                cmd = self.handle_transcript(heard)
                if cmd and self.on_command:
                    try:
                        self.on_command(cmd)
                    except Exception:
                        pass
                    finally:
                        # Caller should set_busy(False) after speak; safety return
                        pass

        self._thread = threading.Thread(target=loop, name="jarvis-wake", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.running = False
        self._emit("idle")

    def _persist_mute(self, muted: bool) -> None:
        try:
            path = user_data_dir() / "ui_prefs.json"
            data = {}
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
            data["mic_muted"] = bool(muted)
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass


def _load_mute_pref() -> bool | None:
    try:
        path = user_data_dir() / "ui_prefs.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if "mic_muted" in data:
            return bool(data["mic_muted"])
    except Exception:
        return None
    return None
