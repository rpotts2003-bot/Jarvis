"""Optional Windows mic STT + SAPI/pyttsx3 TTS. Degrades gracefully if deps missing."""

from __future__ import annotations

import json
import os
import sys
import threading
from typing import Any, Callable

from assistant.voice.adapters import MockSTT, MockTTS, STTAdapter, TTSAdapter
from assistant.voice.tts_style import (
    TtsStyle,
    is_female_voice_label,
    pick_best_voice_id,
    pick_best_voice_name,
)


def _load_tts_style() -> TtsStyle:
    rate = 145
    volume = 0.92
    hint = "George"
    try:
        from assistant.config import load_config

        cfg = load_config()
        voice = cfg.get("voice") or {}
        if isinstance(voice, dict):
            rate = int(voice.get("rate", rate))
            volume = float(voice.get("volume", volume))
            raw_hint = voice.get("voice_hint", hint)
            hint = str(raw_hint if raw_hint is not None else hint) or "George"
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


def _prefs_path():
    from assistant.config import user_data_dir

    return user_data_dir() / "ui_prefs.json"


def _load_ui_prefs() -> dict[str, Any]:
    try:
        path = _prefs_path()
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _save_ui_prefs(updates: dict[str, Any]) -> None:
    try:
        path = _prefs_path()
        data = _load_ui_prefs()
        data.update(updates)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


class SapiTTS(TTSAdapter):
    """Windows TTS: prefer PowerShell System.Speech (reliable male pick), pyttsx3 fallback."""

    def __init__(self, style: TtsStyle | None = None):
        self.style = style or _load_tts_style()
        self._lock = threading.Lock()
        self._engine = None
        self.playing = False
        self.voice_id: str | None = None
        self.voice_name: str | None = None
        self.backend: str = "none"
        self._init_engine()

    def _init_engine(self) -> None:
        self._engine = None
        try:
            import pyttsx3  # type: ignore

            eng = pyttsx3.init()
            voices = list(eng.getProperty("voices") or [])
            prefs = _load_ui_prefs()
            saved_id = prefs.get("tts_voice_id")
            prefer = self.style.voice_hint or "George"

            pick = None
            pick_name = None
            if saved_id and any(getattr(v, "id", None) == saved_id for v in voices):
                # Re-validate saved voice is not female when males exist
                saved_label = ""
                for v in voices:
                    if getattr(v, "id", None) == saved_id:
                        saved_label = f"{getattr(v, 'name', '')} {saved_id}"
                        pick_name = getattr(v, "name", None)
                        break
                males_exist = any(
                    not is_female_voice_label(f"{getattr(v, 'name', '')} {getattr(v, 'id', '')}")
                    for v in voices
                )
                if not (males_exist and is_female_voice_label(saved_label)):
                    pick = saved_id

            if not pick:
                pick = pick_best_voice_id(voices, prefer_hint=prefer)
                pick_name = pick_best_voice_name(voices, prefer_hint=prefer)

            if pick:
                try:
                    eng.setProperty("voice", pick)
                except Exception:
                    pass
                self.voice_id = pick
                self.voice_name = pick_name or pick
                _save_ui_prefs(
                    {
                        "tts_voice_id": self.voice_id,
                        "tts_voice_name": self.voice_name,
                    }
                )
            try:
                eng.setProperty("rate", self.style.rate)
                eng.setProperty("volume", self.style.volume)
            except Exception:
                pass
            self._engine = eng
            self.backend = "pyttsx3"
        except Exception:
            self._engine = None
            if sys.platform.startswith("win"):
                self.backend = "powershell"
                self.voice_name = self.voice_name or (self.style.voice_hint or "George")

    def _reinit_engine(self) -> None:
        try:
            if self._engine is not None:
                try:
                    self._engine.stop()
                except Exception:
                    pass
                try:
                    # Some drivers need endLoop between utterances
                    end = getattr(self._engine, "endLoop", None)
                    if callable(end):
                        end()
                except Exception:
                    pass
        except Exception:
            pass
        self._init_engine()

    @property
    def status_label(self) -> str:
        name = self.voice_name or self.voice_id or "default"
        # Shorten long SAPI names
        short = str(name)
        for prefix in ("Microsoft ", "Desktop - ", "Online (Natural) - "):
            short = short.replace(prefix, "")
        if len(short) > 40:
            short = short[:37] + "…"
        return f"tts:{short}"

    def speak(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        with self._lock:
            self.playing = True
            try:
                # On Windows, PowerShell System.Speech is more reliable for gender/culture
                # and avoids pyttsx3 runAndWait lock after the first utterance.
                if sys.platform.startswith("win") or os.environ.get("JARVIS_FORCE_SAPI"):
                    try:
                        self._speak_powershell(text)
                        self.backend = "powershell"
                        return
                    except Exception:
                        pass
                if self._engine is not None:
                    self._speak_pyttsx3(text)
                    self.backend = "pyttsx3"
                elif sys.platform.startswith("win"):
                    self._speak_powershell(text)
                    self.backend = "powershell"
            finally:
                self.playing = False

    def _speak_pyttsx3(self, text: str) -> None:
        assert self._engine is not None
        try:
            if self.voice_id:
                self._engine.setProperty("voice", self.voice_id)
            self._engine.setProperty("rate", self.style.rate)
            self._engine.setProperty("volume", self.style.volume)
            self._engine.say(text)
            self._engine.runAndWait()
        except Exception:
            self._reinit_engine()
            if self._engine is None:
                raise
            if self.voice_id:
                try:
                    self._engine.setProperty("voice", self.voice_id)
                except Exception:
                    pass
            self._engine.say(text)
            self._engine.runAndWait()

    def _speak_powershell(self, text: str) -> None:
        """System.Speech: en-GB Male / George / any Male before Speak."""
        safe = text.replace("'", "''")
        rate = max(-10, min(10, int((self.style.rate - 200) / 10)))
        hint = (self.style.voice_hint or "George").replace("'", "''")
        saved = (self.voice_name or "").replace("'", "''")
        ps = f"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.Volume = {int(self.style.volume * 100)}
$s.Rate = {rate}
$hint = '{hint}'
$saved = '{saved}'
function Pick-Voice([System.Speech.Synthesis.SpeechSynthesizer]$syn) {{
  $voices = @($syn.GetInstalledVoices() | ForEach-Object {{ $_.VoiceInfo }})
  if ($saved) {{
    $m = $voices | Where-Object {{ $_.Name -eq $saved }} | Select-Object -First 1
    if ($m) {{ return $m }}
  }}
  if ($hint) {{
    $m = $voices | Where-Object {{ $_.Name -match [regex]::Escape($hint) }} | Select-Object -First 1
    if ($m) {{ return $m }}
  }}
  $m = $voices | Where-Object {{ $_.Name -match 'George' }} | Select-Object -First 1
  if ($m) {{ return $m }}
  $m = $voices | Where-Object {{ $_.Culture.Name -eq 'en-GB' -and $_.Gender -eq 'Male' }} | Select-Object -First 1
  if ($m) {{ return $m }}
  $m = $voices | Where-Object {{ $_.Gender -eq 'Male' }} | Select-Object -First 1
  if ($m) {{ return $m }}
  return $null
}}
try {{
  $pick = Pick-Voice $s
  if ($pick) {{
    $s.SelectVoice($pick.Name)
    Write-Output ('JARVIS_VOICE=' + $pick.Name)
  }}
}} catch {{}}
$s.Speak('{safe}')
"""
        import subprocess
        import tempfile
        from pathlib import Path

        path = Path(tempfile.gettempdir()) / "jarvis_speak.ps1"
        path.write_text(ps, encoding="utf-8")
        # Prefer subprocess so we can capture chosen voice name
        try:
            proc = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            out = (proc.stdout or "") + (proc.stderr or "")
            for line in out.splitlines():
                if line.startswith("JARVIS_VOICE="):
                    chosen = line.split("=", 1)[1].strip()
                    if chosen:
                        self.voice_name = chosen
                        _save_ui_prefs({"tts_voice_name": chosen})
                    break
            if proc.returncode != 0 and not out:
                # Fall back to os.system path
                os.system(f'powershell -NoProfile -ExecutionPolicy Bypass -File "{path}"')
        except FileNotFoundError:
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
    """Record a short phrase via sounddevice; recognize with SpeechRecognition.

    Prefer WASAPI shared mode (PortAudio default on Windows). No PyAudio.
    The returned callable has a ``last_error`` attribute:
    None | "network" | "unknown" | "stt" | "mic"
    """
    try:
        import numpy as np  # type: ignore
        import sounddevice as sd  # type: ignore
        import speech_recognition as sr  # type: ignore
    except Exception:
        return None

    recognizer = sr.Recognizer()
    sample_rate = 16000

    def hear() -> str | None:
        hear.last_error = None  # type: ignore[attr-defined]
        try:
            duration = 4.0
            audio = sd.rec(
                int(duration * sample_rate),
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
            )
            sd.wait()
            if on_level:
                peak = float(np.max(np.abs(audio))) if audio is not None else 0.0
                on_level(min(1.0, peak * 4))
            # float32 -1..1 -> int16 PCM for SpeechRecognition
            pcm = (np.clip(audio.flatten(), -1.0, 1.0) * 32767.0).astype(np.int16)
            audio_data = sr.AudioData(pcm.tobytes(), sample_rate, 2)
            try:
                return str(recognizer.recognize_google(audio_data))
            except sr.RequestError:
                hear.last_error = "network"  # type: ignore[attr-defined]
                return None
            except sr.UnknownValueError:
                hear.last_error = "unknown"  # type: ignore[attr-defined]
                return None
            except Exception:
                hear.last_error = "stt"  # type: ignore[attr-defined]
                return None
        except PermissionError:
            raise
        except Exception:
            hear.last_error = "mic"  # type: ignore[attr-defined]
            return None

    hear.last_error = None  # type: ignore[attr-defined]
    return hear


def make_stt() -> STTAdapter:
    return MockSTT()


def gui_uses_noop_orch_tts(orch_tts: TTSAdapter, gui_speak: Callable[[str], None] | None) -> bool:
    """True when GUI owns talkback: orchestrator TTS is a no-op MockTTS and GUI has speak."""
    return isinstance(orch_tts, MockTTS) and gui_speak is not None
