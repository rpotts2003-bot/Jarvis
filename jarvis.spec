# -*- mode: python ; coding: utf-8 -*-
# Build on Windows:  python -m PyInstaller --noconfirm jarvis.spec
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs, collect_submodules

root = Path(SPECPATH)
datas = [
    (str(root / "config.yaml"), "."),
    (str(root / "assistant" / "ui" / "assets"), "assistant/ui/assets"),
    (str(root / ".env.example"), "."),
    (str(root / "VERSION"), "."),
]

hidden = [
    "yaml",
    "assistant",
    "assistant.ui.gui",
    "assistant.ui.orb",
    "assistant.ui.ring_timing",
    "assistant.skills",
    "assistant.skills.registry",
    "assistant.skills.runner",
    "assistant.voice",
    "assistant.voice.wake",
    "assistant.voice.mic_health",
    "assistant.voice.platform_io",
    "assistant.voice.tts_style",
    "assistant.voice.adapters",
    "assistant.voice.state_machine",
    "assistant.envload",
    "assistant.llm.builtins",
    "assistant.llm.intent",
    "assistant.core.orchestrator",
    "assistant.actions.router",
    "assistant.actions.plex",
    "assistant.actions.catalog",
    "assistant.memory.store",
    "assistant.config",
    "tkinter",
    "tkinter.ttk",
]

binaries = []
_missing_critical = []
for pkg in ("speech_recognition", "pyttsx3"):
    try:
        __import__(pkg if pkg != "speech_recognition" else "speech_recognition")
        hidden += collect_submodules(pkg)
        try:
            d, b, h = collect_all(pkg)
            datas += d
            binaries += b
            hidden += h
        except Exception:
            pass
    except Exception:
        _missing_critical.append(pkg)

try:
    import pyaudio  # noqa: F401
    hidden += collect_submodules("pyaudio")
    try:
        binaries += collect_dynamic_libs("pyaudio")
    except Exception:
        pass
except Exception:
    _missing_critical.append("pyaudio")

if _missing_critical:
    print(
        "WARNING: voice packages not importable during freeze:",
        ", ".join(_missing_critical),
        "- install requirements-voice.txt before Build-Exe for mic/TTS in the exe.",
    )

a = Analysis(
    [str(root / "assistant" / "__main__.py")],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "tkinter.test"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Jarvis",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
