"""Optional Windows mic STT + Edge neural / SAPI TTS. Degrades gracefully if deps missing."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Literal

from assistant.voice.adapters import MockSTT, MockTTS, STTAdapter, TTSAdapter
from assistant.voice.tts_style import (
    TtsStyle,
    is_female_voice_label,
    pick_best_voice_id,
    pick_best_voice_name,
    short_edge_voice_name,
)

HearMode = Literal["wake", "ptt"]

# VAD defaults (PTT Listen path)
_VAD_FRAME_S = 0.05
_VAD_WAIT_SPEECH_S = 2.0
_VAD_SILENCE_END_S = 0.85
_VAD_MAX_S = 6.5
_VAD_ENERGY_THRESHOLD = 0.018
_WAKE_DURATION_S = 2.5


def _load_tts_style() -> TtsStyle:
    rate = 175
    volume = 0.92
    hint = "George"
    edge_voice = "en-GB-RyanNeural"
    edge_rate = "+8%"
    try:
        from assistant.config import load_config

        cfg = load_config()
        voice = cfg.get("voice") or {}
        if isinstance(voice, dict):
            rate = int(voice.get("rate", rate))
            volume = float(voice.get("volume", volume))
            raw_hint = voice.get("voice_hint", hint)
            hint = str(raw_hint if raw_hint is not None else hint) or "George"
            raw_ev = voice.get("edge_voice", edge_voice)
            edge_voice = str(raw_ev if raw_ev is not None else edge_voice) or edge_voice
            raw_er = voice.get("edge_rate", edge_rate)
            edge_rate = str(raw_er if raw_er is not None else edge_rate) or edge_rate
    except Exception:
        pass
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
    if os.environ.get("JARVIS_EDGE_VOICE"):
        edge_voice = os.environ["JARVIS_EDGE_VOICE"]
    if os.environ.get("JARVIS_EDGE_RATE"):
        edge_rate = os.environ["JARVIS_EDGE_RATE"]
    return TtsStyle(
        rate=rate,
        volume=max(0.0, min(1.0, volume)),
        voice_hint=hint,
        edge_voice=edge_voice,
        edge_rate=edge_rate,
    )


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


# ---------------------------------------------------------------------------
# Pure VAD helpers (unit-tested)
# ---------------------------------------------------------------------------


def pcm_rms(frame) -> float:
    """RMS energy of a float mono frame (numpy array or sequence)."""
    try:
        import numpy as np  # type: ignore

        arr = np.asarray(frame, dtype=np.float64).reshape(-1)
        if arr.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(arr * arr)))
    except Exception:
        try:
            vals = list(frame)
            if not vals:
                return 0.0
            mean_sq = sum(float(x) * float(x) for x in vals) / len(vals)
            return mean_sq**0.5
        except Exception:
            return 0.0


def speech_detected(rms: float, threshold: float = _VAD_ENERGY_THRESHOLD) -> bool:
    return float(rms) >= float(threshold)


def should_end_on_silence(silence_s: float, needed_s: float = _VAD_SILENCE_END_S) -> bool:
    return float(silence_s) >= float(needed_s)


def level_from_rms(rms: float, *, gain: float = 12.0) -> float:
    """Map RMS to 0..1 VU for the orb."""
    return max(0.0, min(1.0, float(rms) * gain))


# ---------------------------------------------------------------------------
# SAPI / pyttsx3 fallback
# ---------------------------------------------------------------------------


class SapiTTS(TTSAdapter):
    """Windows TTS: prefer warm pyttsx3 engine; PowerShell System.Speech fallback."""

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
                # Prefer warm pyttsx3 (no PowerShell spawn per utterance).
                if self._engine is not None:
                    try:
                        self._speak_pyttsx3(text)
                        self.backend = "pyttsx3"
                        return
                    except Exception:
                        pass
                if sys.platform.startswith("win") or os.environ.get("JARVIS_FORCE_SAPI"):
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

        path = Path(tempfile.gettempdir()) / "jarvis_speak.ps1"
        path.write_text(ps, encoding="utf-8")
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


# ---------------------------------------------------------------------------
# Edge TTS (neural UK male — free, needs internet)
# ---------------------------------------------------------------------------

_EDGE_FALLBACK_VOICES = ("en-GB-RyanNeural", "en-GB-ThomasNeural")


def _edge_tts_importable() -> bool:
    try:
        import edge_tts  # noqa: F401

        return True
    except Exception:
        return False


class EdgeTTS(TTSAdapter):
    """Synthesize via edge-tts to temp mp3; play with Windows MediaPlayer / MCI."""

    def __init__(self, style: TtsStyle | None = None):
        self.style = style or _load_tts_style()
        self._lock = threading.Lock()
        self.playing = False
        self.backend: str = "edge"
        self.voice_id = self._pick_voice()
        self.voice_name = short_edge_voice_name(self.voice_id)
        self._fallback = SapiTTS(self.style)
        self._warmed = False

    def _pick_voice(self) -> str:
        preferred = (self.style.edge_voice or "").strip() or _EDGE_FALLBACK_VOICES[0]
        if preferred in _EDGE_FALLBACK_VOICES:
            return preferred
        # Allow custom override; still keep Ryan/Thomas as known good
        return preferred

    @property
    def status_label(self) -> str:
        if self.backend.startswith("edge"):
            return f"tts:{self.voice_name or short_edge_voice_name(self.voice_id)}"
        return self._fallback.status_label

    def _voices_to_try(self) -> list[str]:
        ordered: list[str] = []
        for v in (self.voice_id, *_EDGE_FALLBACK_VOICES):
            if v and v not in ordered:
                ordered.append(v)
        return ordered

    async def _synth_to_file(self, text: str, path: Path, voice: str) -> None:
        import edge_tts  # type: ignore

        rate = self.style.edge_rate or "+8%"
        # volume: edge uses ±N%; map 0..1 roughly to 0% at 1.0
        vol_pct = int(round((self.style.volume - 1.0) * 100))
        vol_pct = max(-50, min(50, vol_pct))
        volume = f"{vol_pct:+d}%"
        communicate = edge_tts.Communicate(text, voice, rate=rate, volume=volume)
        await communicate.save(str(path))

    def _synthesize(self, text: str, path: Path) -> str:
        """Try preferred + fallback neural voices. Returns voice id used."""
        last_err: Exception | None = None
        for voice in self._voices_to_try():
            try:
                asyncio.run(self._synth_to_file(text, path, voice))
                if path.exists() and path.stat().st_size > 0:
                    self.voice_id = voice
                    self.voice_name = short_edge_voice_name(voice)
                    return voice
            except Exception as e:  # noqa: BLE001
                last_err = e
                try:
                    if path.exists():
                        path.unlink(missing_ok=True)  # type: ignore[call-arg]
                except Exception:
                    pass
        if last_err:
            raise last_err
        raise RuntimeError("edge-tts synthesis failed")

    def _play_mp3_windows(self, path: Path) -> None:
        """Play mp3 via PowerShell MediaPlayer (no mpv). Blocks until done."""
        import subprocess

        uri = path.resolve().as_uri()
        safe_uri = uri.replace("'", "''")
        ps = f"""
Add-Type -AssemblyName presentationCore
$p = New-Object System.Windows.Media.MediaPlayer
$p.Volume = {max(0.0, min(1.0, self.style.volume))}
$p.Open([Uri]'{safe_uri}')
$sw = [Diagnostics.Stopwatch]::StartNew()
while (-not $p.NaturalDuration.HasTimeSpan) {{
  Start-Sleep -Milliseconds 50
  if ($sw.Elapsed.TotalSeconds -gt 15) {{ break }}
}}
$p.Play()
if ($p.NaturalDuration.HasTimeSpan) {{
  $ms = [int]($p.NaturalDuration.TimeSpan.TotalMilliseconds) + 200
  Start-Sleep -Milliseconds $ms
}} else {{
  Start-Sleep -Seconds 8
}}
$p.Stop()
$p.Close()
"""
        script = Path(tempfile.gettempdir()) / "jarvis_edge_play.ps1"
        script.write_text(ps, encoding="utf-8")
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
            ],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )

    def _play_mp3(self, path: Path) -> None:
        if sys.platform.startswith("win"):
            self._play_mp3_windows(path)
            return
        # Non-Windows best-effort (dev box): try ffplay / mpg123 quietly
        import shutil
        import subprocess

        for cmd in (
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)],
            ["mpg123", "-q", str(path)],
        ):
            if shutil.which(cmd[0]):
                subprocess.run(cmd, capture_output=True, timeout=180, check=False)
                return

    def speak(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        with self._lock:
            self.playing = True
            path: Path | None = None
            try:
                fd, name = tempfile.mkstemp(prefix="jarvis_edge_", suffix=".mp3")
                os.close(fd)
                path = Path(name)
                self._synthesize(text, path)
                self._play_mp3(path)
                self.backend = "edge"
                self._warmed = True
            except Exception:
                self.backend = "sapi-fallback"
                self._fallback.speak(text)
            finally:
                self.playing = False
                if path is not None:
                    try:
                        path.unlink(missing_ok=True)  # type: ignore[call-arg]
                    except Exception:
                        try:
                            path.unlink()
                        except Exception:
                            pass

    def stop(self) -> None:
        self.playing = False
        try:
            self._fallback.stop()
        except Exception:
            pass


def make_tts() -> TTSAdapter:
    style = _load_tts_style()
    force_sapi = os.environ.get("JARVIS_FORCE_SAPI", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if os.environ.get("JARVIS_FORCE_SAPI") == "0":
        return MockTTS()
    prefer_edge = os.environ.get("JARVIS_TTS_BACKEND", "edge").strip().lower() != "sapi"
    allow_edge = (
        sys.platform.startswith("win")
        or os.environ.get("JARVIS_ALLOW_EDGE") == "1"
        or os.environ.get("JARVIS_FORCE_EDGE") == "1"
    )
    # Prefer edge-tts neural when importable (online at speak-time; SAPI on failure)
    if prefer_edge and not force_sapi and allow_edge and _edge_tts_importable():
        return EdgeTTS(style)
    if sys.platform.startswith("win") or force_sapi:
        return SapiTTS(style)
    return MockTTS()


# ---------------------------------------------------------------------------
# Mic / STT
# ---------------------------------------------------------------------------


def _recognize_google(recognizer, pcm_bytes: bytes, sample_rate: int, hear_fn) -> str | None:
    import speech_recognition as sr  # type: ignore

    audio_data = sr.AudioData(pcm_bytes, sample_rate, 2)
    try:
        return str(recognizer.recognize_google(audio_data))
    except sr.RequestError:
        hear_fn.last_error = "network"  # type: ignore[attr-defined]
        return None
    except sr.UnknownValueError:
        hear_fn.last_error = "unknown"  # type: ignore[attr-defined]
        return None
    except Exception:
        hear_fn.last_error = "stt"  # type: ignore[attr-defined]
        return None


def _record_fixed(
    *,
    duration: float,
    sample_rate: int,
    on_level: Callable[[float], None] | None,
):
    import numpy as np  # type: ignore
    import sounddevice as sd  # type: ignore

    frames = int(duration * sample_rate)
    audio = sd.rec(frames, samplerate=sample_rate, channels=1, dtype="float32")
    # Rough mid-record VU
    if on_level:
        on_level(0.25)
    sd.wait()
    if on_level:
        peak = float(np.max(np.abs(audio))) if audio is not None else 0.0
        on_level(level_from_rms(peak / 2.0 if peak else 0.0))
    flat = np.clip(audio.flatten(), -1.0, 1.0)
    if float(np.max(np.abs(flat))) < 1e-5:
        return flat, True  # flat mic
    pcm = (flat * 32767.0).astype(np.int16)
    return pcm, False


def _record_vad_ptt(
    *,
    sample_rate: int,
    on_level: Callable[[float], None] | None,
    energy_threshold: float = _VAD_ENERGY_THRESHOLD,
):
    """Energy VAD: wait for speech, then until silence or max duration.

    Returns (pcm_int16_or_float_empty, flat_mic: bool, heard_speech: bool).
    """
    import numpy as np  # type: ignore
    import sounddevice as sd  # type: ignore

    frame = int(_VAD_FRAME_S * sample_rate)
    chunks: list = []
    speech_started = False
    silence_s = 0.0
    waited_s = 0.0
    spoken_s = 0.0
    flat_streak = 0

    with sd.InputStream(samplerate=sample_rate, channels=1, dtype="float32", blocksize=frame) as stream:
        while True:
            data, overflowed = stream.read(frame)  # noqa: F841
            mono = data.reshape(-1)
            rms = pcm_rms(mono)
            if on_level:
                on_level(level_from_rms(rms))

            if rms < 1e-6:
                flat_streak += 1
            else:
                flat_streak = 0

            if not speech_started:
                waited_s += _VAD_FRAME_S
                if speech_detected(rms, energy_threshold):
                    speech_started = True
                    silence_s = 0.0
                    chunks.append(mono.copy())
                    spoken_s += _VAD_FRAME_S
                elif waited_s >= _VAD_WAIT_SPEECH_S:
                    # Never crossed energy — didn't hear you
                    empty = np.zeros(0, dtype=np.float32)
                    is_flat = flat_streak * _VAD_FRAME_S >= min(1.0, _VAD_WAIT_SPEECH_S * 0.8)
                    return empty, is_flat, False
            else:
                chunks.append(mono.copy())
                spoken_s += _VAD_FRAME_S
                if speech_detected(rms, energy_threshold * 0.7):
                    silence_s = 0.0
                else:
                    silence_s += _VAD_FRAME_S
                if should_end_on_silence(silence_s, _VAD_SILENCE_END_S):
                    break
                if spoken_s >= _VAD_MAX_S:
                    break

    if not chunks:
        return np.zeros(0, dtype=np.float32), True, False
    audio = np.concatenate(chunks)
    flat = np.clip(audio.astype(np.float32), -1.0, 1.0)
    if float(np.max(np.abs(flat))) < 1e-5:
        return flat, True, speech_started
    pcm = (flat * 32767.0).astype(np.int16)
    return pcm, False, speech_started


def make_mic_hear(
    *,
    on_level: Callable[[float], None] | None = None,
    mode: HearMode = "ptt",
) -> Callable[[], str | None] | None:
    """Record via sounddevice; recognize with SpeechRecognition (Google STT).

    mode=\"ptt\": energy VAD for Listen button (Speak now…).
    mode=\"wake\": shorter fixed ~2.5s chunk for wake loop.

    The returned callable has attributes:
      last_error: None | \"network\" | \"unknown\" | \"stt\" | \"mic\"
      on_level: optional VU callback (mutable)
      mode: wake|ptt
    """
    try:
        import numpy as np  # noqa: F401
        import sounddevice as sd  # noqa: F401
        import speech_recognition as sr  # type: ignore
    except Exception:
        return None

    recognizer = sr.Recognizer()
    sample_rate = 16000

    def hear() -> str | None:
        hear.last_error = None  # type: ignore[attr-defined]
        level_cb = hear.on_level  # type: ignore[attr-defined]
        use_mode: HearMode = hear.mode  # type: ignore[attr-defined]
        try:
            if use_mode == "wake":
                pcm, is_flat = _record_fixed(
                    duration=_WAKE_DURATION_S,
                    sample_rate=sample_rate,
                    on_level=level_cb,
                )
                heard_speech = not is_flat
            else:
                pcm, is_flat, heard_speech = _record_vad_ptt(
                    sample_rate=sample_rate,
                    on_level=level_cb,
                )

            if not heard_speech or getattr(pcm, "size", 0) == 0:
                # Never crossed energy / empty — not network. Flat device → mic; else unknown.
                hear.last_error = "mic" if is_flat else "unknown"  # type: ignore[attr-defined]
                return None


            pcm_bytes = pcm.tobytes() if hasattr(pcm, "tobytes") else bytes(pcm)
            return _recognize_google(recognizer, pcm_bytes, sample_rate, hear)
        except PermissionError:
            raise
        except Exception:
            hear.last_error = "mic"  # type: ignore[attr-defined]
            return None

    hear.last_error = None  # type: ignore[attr-defined]
    hear.on_level = on_level  # type: ignore[attr-defined]
    hear.mode = mode  # type: ignore[attr-defined]
    return hear


def make_mic_hear_ptt(
    *,
    on_level: Callable[[float], None] | None = None,
) -> Callable[[], str | None] | None:
    """Listen-button path: energy VAD + Google STT."""
    return make_mic_hear(on_level=on_level, mode="ptt")


def make_stt() -> STTAdapter:
    return MockSTT()


def gui_uses_noop_orch_tts(orch_tts: TTSAdapter, gui_speak: Callable[[str], None] | None) -> bool:
    """True when GUI owns talkback: orchestrator TTS is a no-op MockTTS and GUI has speak."""
    return isinstance(orch_tts, MockTTS) and gui_speak is not None
