"""Always-on listen: only accept utterances after the wake name; support mute."""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class WakeConfig:
    wake_name: str = "Jarvis"
    # After wake, keep capturing follow-on words briefly
    followup_window_s: float = 6.0
    poll_s: float = 0.25


@dataclass
class WakeListener:
    """Headless always-listen controller (STT backend plugged in separately)."""

    config: WakeConfig = field(default_factory=WakeConfig)
    muted: bool = False
    running: bool = False
    on_command: Callable[[str], None] | None = None
    on_state: Callable[[str], None] | None = None  # idle|listening|muted|wake
    _thread: threading.Thread | None = None
    _stop: threading.Event = field(default_factory=threading.Event)
    # inject: callable that blocks until a phrase transcript or returns "" / None on timeout
    hear: Callable[[], str | None] | None = None

    def _wake_re(self) -> re.Pattern[str]:
        name = re.escape(self.config.wake_name.strip())
        # optional "hey" / "ok" before the name
        return re.compile(rf"(?:(?:hey|ok|okay)\s+)?\b{name}\b", re.I)

    def strip_wake(self, text: str) -> str:
        t = (text or "").strip()
        t = self._wake_re().sub("", t, count=1)
        return re.sub(r"^[\s,.:;!\-]+", "", t).strip()

    def set_muted(self, muted: bool) -> None:
        self.muted = muted
        if self.on_state:
            self.on_state("muted" if muted else ("listening" if self.running else "idle"))

    def toggle_mute(self) -> bool:
        self.set_muted(not self.muted)
        return self.muted

    def handle_transcript(self, text: str) -> str | None:
        """Process one heard phrase. Returns command text if wake matched, else None."""
        if self.muted or not text:
            return None
        raw = text.strip()
        if not self._wake_re().search(raw):
            return None
        cmd = self.strip_wake(raw)
        if self.on_state:
            self.on_state("wake")
        if cmd:
            return cmd
        # Bare wake name — wait for a follow-up phrase if hear() available
        if self.hear:
            follow = self.hear() or ""
            follow = follow.strip()
            if follow:
                if self._wake_re().search(follow):
                    follow = self.strip_wake(follow)
                return follow or None
        return None

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._stop.clear()
        if self.on_state:
            self.on_state("muted" if self.muted else "listening")
        if self.hear is None:
            return  # GUI may feed transcripts manually / no mic backend

        def loop() -> None:
            while not self._stop.is_set():
                if self.muted:
                    time.sleep(self.config.poll_s)
                    continue
                try:
                    heard = self.hear() if self.hear else None
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

        self._thread = threading.Thread(target=loop, name="jarvis-wake", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.running = False
        if self.on_state:
            self.on_state("idle")
