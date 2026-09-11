"""Optional Windows mic STT + SAPI/pyttsx3 TTS. Degrades gracefully if deps missing."""

from __future__ import annotations

import os
import re
import sys
import threading
from typing import Callable

from assistant.voice.adapters import MockSTT, MockTTS, STTAdapter, TTSAdapter


class SapiTTS(TTSAdapter):
    """Windows SAPI via pyttsx3, or PowerShell System.Speech fallback."""

    def __init__(self):
        self._lock = threading.Lock()
        self._engine = None
        self.playing = False
        try:
            import pyttsx3  # type: ignore

            self._engine = pyttsx3.init()
            # Prefer a British male voice (Iron Man Jarvis style target — not a clone)
            try:
                voices = self._engine.getProperty("voices") or []
                pick = None
                for v in voices:
                    name = f"{getattr(v, 'name', '')} {getattr(v, 'id', '')}".lower()
                    if any(k in name for k in ("british", "uk", "england", "george", "hazel", "ryan", "thomas")):
                        # prefer male-ish ids when obvious
                        pick = v.id
                        if any(k in name for k in ("male", "george", "david", "mark", "ryan", "thomas", "ravi")):
                            pick = v.id
                            break
                if pick:
                    self._engine.setProperty("voice", pick)
                # Measured pace (Jarvis never rushes)
                self._engine.setProperty("rate", 155)
            except Exception:
                pass
        except Exception:
            self._engine = None

    def speak(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        with self._lock:
            self.playing = True
            try:
                if self._engine is not None:
                    self._engine.say(text)
                    self._engine.runAndWait()
                elif sys.platform.startswith("win"):
                    # Escape for PowerShell single-quoted string
                    safe = text.replace("'", "''")
                    os.system(
                        "powershell -NoProfile -Command "
                        "\"Add-Type -AssemblyName System.Speech; "
                        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                        f"$s.Speak('{safe}')\""
                    )
            finally:
                self.playing = False

    def stop(self) -> None:
        try:
            if self._engine is not None:
                self._engine.stop()
        except Exception:
            pass
        self.playing = False


def make_tts() -> TTSAdapter:
    if sys.platform.startswith("win") or os.environ.get("JARVIS_FORCE_SAPI"):
        return SapiTTS()
    return MockTTS()


def make_mic_hear(
    *,
    on_level: Callable[[float], None] | None = None,
) -> Callable[[], str | None] | None:
    """Return a blocking hear() using SpeechRecognition, or None if unavailable."""
    try:
        import speech_recognition as sr  # type: ignore
    except Exception:
        return None

    recognizer = sr.Recognizer()
    recognizer.dynamic_energy_threshold = True
    try:
        mic = sr.Microphone()
    except Exception:
        return None

    def hear() -> str | None:
        try:
            with mic as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.3)
                audio = recognizer.listen(source, timeout=2, phrase_time_limit=5)
            if on_level:
                on_level(0.4)
            # Prefer local Whisper if installed; else Google (needs net) as last resort
            try:
                text = recognizer.recognize_whisper(audio, model="base")  # type: ignore[attr-defined]
                return str(text)
            except Exception:
                pass
            try:
                text = recognizer.recognize_google(audio)
                return str(text)
            except Exception:
                return None
        except Exception:
            return None

    return hear


def make_stt() -> STTAdapter:
    return MockSTT()
