# Jarvis architecture (9am rebuild)

## Goal

Windows desktop assistant: **bundled local free-form chat** (GGUF via `llama-cpp-python`), mic Listen + wake word, cyan HUD orb, allowlisted PC actions. Built-ins stay offline extras. No required Ollama or cloud key.

## Stack comparison (this morning)

| Option | Mic + STT | HUD | Local LLM | Ship time today | Notes |
|--------|-----------|-----|-----------|-----------------|-------|
| **Python + tkinter (current)** | sounddevice + SpeechRecognition already wired | Canvas HUD works; procedural orb | Jarvis downloads GGUF → `llama-cpp-python` | **Hours** | Repo, tests, Start Jarvis.bat, voice path exist |
| **Electron** | Node bindings / spawn Python helper | Rich Chromium UI | Same brain over IPC | Days for parity | Dual runtime; larger installer; rewrite Listen/wake |
| **Tauri** | Rust crates or sidecar | Webview UI | Same | Days+ | Best long-term desktop shell; greenfield vs this checkout |
| **.NET (WPF/WinUI)** | NAudio + Windows speech APIs | Native XAML | Same | Days | Strong on Windows; full rewrite of brain/skills |

## Recommendation (Phase A — ship this morning)

**Keep Python for brain + mic + chat.** Replace the PhotoImage orb with a **procedural canvas arc-reactor**. Document Electron/Tauri as **Phase-2** if we need a richer chrome UI later.

Honesty: Jarvis manages a downloaded GGUF file (default Qwen2.5-1.5B-Instruct Q4_K_M ~1.04 GB) — it does not train a model from scratch, and it does not require a separate Ollama install.

## Runtime shape (Python)

```
Start Jarvis.bat → .venv → pip (voice + try llama-cpp-python) → python -m assistant gui
  ├── Orchestrator (builtins → skills → actions → chat_reply)
  ├── chat_reply: bundled GGUF → optional Ollama (JARVIS_LOCAL_LLM=1 only) → optional cloud → tip
  ├── WakeListener + make_mic_hear (Windows Speech Listen / sounddevice wake)
  └── JarvisWindow (tk Canvas HUD + Mute / Listen / typed input; async submit)
```

Model path: `%USERPROFILE%\.jarvis\models\` via `user_data_dir()`. Status file: `download_status.json` (HUD-friendly). Chip: `chat:local` | `chat:downloading` | `chat:offline`.

## Phase-2 (optional)

- Tauri or Electron shell hosting the same Python brain over localhost IPC, or a gradual UI rewrite.
- Offline STT (Whisper.cpp) to drop Google dependency for Listen/wake.

## Non-goals this morning

- Cloud Agents / Cursor Pro remote builds
- Locking architecture to a new stack without a further-along Windows prototype
