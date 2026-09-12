# Jarvis (desktop MVP)

Local-first desktop assistant: push-to-talk ready state machine, teachable memory, allowlisted PC actions, and a listening orb (Idle / Listening / Thinking / Speaking).

> Core intent + memory + actions run offline. Free-form chat uses a **GGUF language-model file that Jarvis downloads and manages itself** under `%USERPROFILE%\.jarvis\models\` (no separate Ollama app, no required OpenAI/Grok key). Voice uses Windows TTS + Google STT (online) via `sounddevice`; cloud chat keys are optional only.

## Honesty

Jarvis does **not** train a GPT from scratch. On first use it downloads a small open instruct model (default **Qwen2.5-1.5B-Instruct Q4_K_M**, ~**1.04 GB**) and runs it locally with `llama-cpp-python`. That file is owned/managed by Jarvis in its own data folder — you do not install a separate AI app.

## Double-click Start Jarvis.bat. That's it.

On Windows (ZIP download):

1. Unzip the folder.
2. **Double-click `Start Jarvis.bat`.**
3. First run creates `.venv`, installs core + voice packages, installs `llama-cpp-python` from a **prebuilt CPU wheel** (`--extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu`, `--only-binary` first so it does not compile from source), copies `.env.example` → `.env` if needed, then opens the HUD.
4. Later runs skip reinstall unless packages are missing.

If Python is missing, the bat stops with plain English steps (install from python.org with **Add to PATH** and **tcl/tk**). Mic problems only warn — the window still opens and **typing works**. If `llama-cpp-python` fails to install, the bat prints a clear message; builtins still work.

### First chat (brain download)

1. Start Jarvis.bat
2. Wait for the status chip to move from `chat:downloading` → `chat:local` (or type a free-form question — Jarvis starts the download and replies “Downloading brain… try again in a minute.”)
3. Type `hello` or `call me sir` — builtins always work; free-form chat uses the local model once ready.

**No Ollama. First chat may download ~1.04 GB once.**

Optional: set `OPENAI_API_KEY` for cloud fallback, or `JARVIS_LOCAL_LLM=1` only if you *want* Ollama. Set `JARVIS_DISABLE_LOCAL_LLM=1` to skip the bundled brain. Overrides: `JARVIS_MODEL_URL`, `JARVIS_MODEL_FILE`.

Your saved lessons live in `%USERPROFILE%\.jarvis\` so they survive updates.

## Desktop window

The HUD shows a procedural cyan arc-reactor orb on a dark grid, a one-line caption, and Mute / Listen / typed input. Status chip: `chat:local` (brain ready), `chat:downloading`, or `chat:offline`. Built-ins work without teaching: `hi`, `help`, `what time is it`.

## Teach it

```
> learn when I say morning do open calculator
Got it — learn "morning" → open calculator? Say yes to save.
> yes
Got it — saved.
> morning
Opened calculator
> list skills
```

Also: `next time I say downloads, do open chrome` · `remember that my name is R.P.`

## Voice

Speech uses free neural UK male via Edge TTS (`en-GB-RyanNeural`, needs internet); offline falls back to Windows SAPI (*George*). Soft tip: UK speech pack still helps the offline fallback.

Jarvis listens after you say its name (`Jarvis` by default), or tap **Listen** on the HUD for one command without the wake word. Use **Mute** to silence the mic. Typed replies are spoken aloud. Typing always works if the mic fails.

Say `diagnose` or `test mic`, or use **Test mic** on the HUD.

## Safety

- Allowlisted apps / folder roots / https URLs only
- No free-form shell, delete, or `file://` / `javascript:` URLs
- Medium-risk actions need a `yes` confirm

## Config

See `config.yaml` and `ARCHITECTURE.md`. Copy `.env.example` to `.env` for model overrides / optional cloud (`JARVIS_CLOUD_CHAT=0` forces offline cloud fallback).

## Plex library import (local files only)

Jarvis will **not** download movies from the web. It can copy/move files you already have into your Plex Movies folder. Set `plex.library_dir` in `config.yaml`, keep sources under allowlisted roots, then `add ~/Downloads/MyMovie.mp4 to plex` → `yes` → `scan plex`.

## Advanced

- **One-file exe:** run `scripts\Build-Exe.bat`, then double-click `dist\Jarvis.exe` (optional `.env` beside the exe). No bat/venv needed at runtime.
- **PowerShell setup:** `scripts\setup.ps1` (or `-SkipMic`) for advanced troubleshooting. Beginners should use `Start Jarvis.bat` only.
- **Dev:** `python -m venv .venv` → activate → `pip install -r requirements.txt` → `pytest -q` → `python -m assistant gui`

**Before every push:** `python scripts/preflight.py` must print `PREFLIGHT PASSED`.
