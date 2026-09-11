"""Optional Windows mic STT + SAPI/pyttsx3 TTS. Degrades gracefully if deps missing."""

from __future__ import annotations

import os
import sys
import threading
from typing import Any, Callable

from assistant.voice.adapters import MockSTT, MockTTS, STTAdapter, TTSAdapter
from assistant.voice.tts_style import TtsStyle, pick_best_voice_id


def _load_tts_style() -> TtsStyle:
    rate = 145
    volume = 0.92
    hint = ""
    try:
        from assistant.config import load_config

        cfg = load_config()
        voice = cfg.get("voice") or {}
        if isinstance(voice, dict):
            rate = int(voice.get("rate", rate))
            volume = float(voice.get("volume", volume))
            hint = str(voice.get("voice_hint", hint) or "")
    except Exception:
        pass
    # Env overrides
    if os.environ.get("JARVIS_TTS_RATE"):
        try:
            rate = int(os.environ["JARVIS_TTS_RATE"])
        except ValueError:
            pass
    if os.environ.get("JARVIS_TTS_VOLUME"):
        try:
            volume = float(os.environ["JARVIS_TTS_VOLUME"])
        except ValueError:
            pass
    if os.environ.get("JARVIS_TTS_VOICE"):
        hint = os.environ["JARVIS_TTS_VOICE"]
    return TtsStyle(rate=rate, volume=max(0.0, min(1.0, volume)), voice_hint=hint)


class SapiTTS(TTSAdapter):
    """Windows SAPI via pyttsx3, or PowerShell System.Speech fallback."""

    def __init__(self, style: TtsStyle | None = None):
        self.style = style or _load_tts_style()
        self._lock = threading.Lock()
        self._engine = None
        self.playing = False
        self.voice_id: str | None = None
        try:
            import pyttsx3  # type: ignore

            self._engine = pyttsx3.init()
            try:
                voices = list(self._engine.getProperty("voices") or [])
                pick = pick_best_voice_id(voices, prefer_hint=self.style.voice_hint)
                if pick:
                    self._engine.setProperty("voice", pick)
                    self.voice_id = pick
                self._engine.setProperty("rate", self.style.rate)
                self._engine.setProperty("volume", self.style.volume)
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
                    self._speak_powershell(text)
            finally:
                self.playing = False

    def _speak_powershell(self, text: str) -> None:
        """Fallback: System.Speech with UK male preference when possible."""
        safe = text.replace("'", "''")
        # Prefer George / en-GB voices via SelectVoiceByHints if available
        rate = max(-10, min(10, int((self.style.rate - 200) / 10)))
        ps = f"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.Volume = {int(self.style.volume * 100)}
$s.Rate = {rate}
try {{
  $uk = $s.GetInstalledVoices() | Where-Object {{
    $_.VoiceInfo.Culture.Name -eq 'en-GB' -and $_.VoiceInfo.Gender -eq 'Male'
  }} | Select-Object -First 1
  if ($uk) {{ $s.SelectVoice($uk.VoiceInfo.Name) }}
  else {{
    $g = $s.GetInstalledVoices() | Where-Object {{ $_.VoiceInfo.Name -match 'George' }} | Select-Object -First 1
    if ($g) {{ $s.SelectVoice($g.VoiceInfo.Name) }}
  }}
}} catch {{}}
$s.Speak('{safe}')
"""
        # Write temp script to avoid quoting hell
        import tempfile
        from pathlib import Path

        path = Path(tempfile.gettempdir()) / "jarvis_speak.ps1"
        path.write_text(ps, encoding="utf-8")
        os.system(f'powershell -NoProfile -ExecutionPolicy Bypass -File "{path}"')

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
    # Non-Windows: still allow style object for tests
    if os.environ.get("JARVIS_FORCE_SAPI") == "0":
        return MockTTS()
    return MockTTS()


def make_mic_hear(
    *,
    on_level: Callable[[float], None] | None = None,
) -> Callable[[], str | None] | None:
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
            try:
                return str(recognizer.recognize_whisper(audio, model="base"))  # type: ignore[attr-defined]
            except Exception:
                pass
            try:
                return str(recognizer.recognize_google(audio))
            except Exception:
                return None
        except Exception:
            return None

    return hear


def make_stt() -> STTAdapter:
    return MockSTT()
