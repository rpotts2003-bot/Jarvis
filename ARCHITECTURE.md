# Jarvis architecture (9am rebuild)

## Goal

Windows desktop assistant: **local free-form chat** (Ollama), mic Listen + wake word, cyan HUD orb, allowlisted PC actions. Built-ins stay offline extras.

## Stack comparison (this morning)

| Option | Mic + STT | HUD | Ollama | Ship time today | Notes |
|--------|-----------|-----|--------|-----------------|-------|
| **Python + tkinter (current)** | sounddevice + SpeechRecognition already wired | Canvas HUD works; PhotoImage orb was weak | OpenAI-compatible HTTP → localhost:11434 | **Hours** | Repo, tests, Start Jarvis.bat, voice path exist |
| **Electron** | Node bindings / spawn Python helper | Rich Chromium UI | Easy fetch to Ollama | Days for parity | Dual runtime; larger installer; rewrite Listen/wake |
| **Tauri** | Rust crates or sidecar | Webview UI | Easy | Days+ | Best long-term desktop shell; greenfield vs this checkout |
| **.NET (WPF/WinUI)** | NAudio + Windows speech APIs | Native XAML | HttpClient to Ollama | Days | Strong on Windows; full rewrite of brain/skills |

## Recommendation (Phase A — ship this morning)

**Keep Python for brain + mic + chat.** Replace the PhotoImage orb with a **procedural canvas arc-reactor**. Document Electron/Tauri as **Phase-2** if we need a richer chrome UI later.

Honesty: a minimal Tauri/Electron prototype would not beat fixing the existing Python path today (Listen, wake, builtins, memory, Plex, bat launcher, preflight).

## Runtime shape (Python)

```
Start Jarvis.bat → .venv → python -m assistant gui
  ├── Orchestrator (builtins → skills → actions → chat_reply)
  ├── chat_reply: Ollama local first → optional cloud key → offline tip
  ├── WakeListener + make_mic_hear (fixed ~5s Listen / shorter wake)
  └── JarvisWindow (tk Canvas HUD + Mute / Listen / typed input)
```

## Phase-2 (optional)

- Tauri or Electron shell hosting the same Python brain over localhost IPC, or a gradual UI rewrite.
- Offline STT (Whisper.cpp) to drop Google dependency for Listen/wake.

## Non-goals this morning

- Cloud Agents / Cursor Pro remote builds
- Locking architecture to a new stack without a further-along Windows prototype
