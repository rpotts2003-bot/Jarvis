# -*- mode: python ; coding: utf-8 -*-
# Build on Windows:  python -m PyInstaller --noconfirm jarvis.spec
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH)
datas = [
    (str(root / "config.yaml"), "."),
    (str(root / "assistant" / "ui" / "assets"), "assistant/ui/assets"),
    (str(root / ".env.example"), "."),
]

hidden = [
    "yaml",
    "assistant",
    "assistant.ui.gui",
    "assistant.ui.ring_timing",
    "assistant.skills.registry",
    "assistant.skills.runner",
    "assistant.voice.wake",
    "assistant.voice.mic_health",
    "assistant.voice.platform_io",
    "assistant.voice.tts_style",
    "assistant.envload",
]
# Optional voice deps — include if installed so exe doesn't miss them
for pkg in ("speech_recognition", "pyttsx3", "pyaudio"):
    try:
        hidden += collect_submodules(pkg)
    except Exception:
        pass

a = Analysis(
    [str(root / "assistant" / "__main__.py")],
    pathex=[str(root)],
    binaries=[],
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
    console=False,  # GUI app — no black console window
    disable_windowed_traceback=False,
)
