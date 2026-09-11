from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable


class STTAdapter(ABC):
    @abstractmethod
    def transcribe(self, pcm16k_mono: bytes) -> str:
        ...


class TTSAdapter(ABC):
    @abstractmethod
    def speak(self, text: str) -> None:
        ...

    @abstractmethod
    def stop(self) -> None:
        ...


class MockSTT(STTAdapter):
    def __init__(self, scripted: str = ""):
        self.scripted = scripted
        self.calls = 0
        self.fail_missing_model = False
        self.hang = False

    def transcribe(self, pcm16k_mono: bytes) -> str:
        self.calls += 1
        if self.fail_missing_model:
            raise FileNotFoundError("model missing")
        if self.hang:
            raise TimeoutError("stt hang")
        return self.scripted


class MockTTS(TTSAdapter):
    def __init__(self):
        self.spoken: list[str] = []
        self.stopped = 0
        self.playing = False

    def speak(self, text: str) -> None:
        self.playing = True
        self.spoken.append(text)
        self.playing = False

    def stop(self) -> None:
        self.stopped += 1
        self.playing = False
