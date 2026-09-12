# Jarvis (desktop MVP)

Local-first desktop assistant: push-to-talk ready state machine, teachable memory, allowlisted PC actions, and a listening orb (Idle / Listening / Thinking / Speaking).

> Core intent + memory + actions run offline. Voice uses Windows TTS + Google STT (online) via `sounddevice`; optional OpenAI chat needs a key in `.env`.

## Double-click Start Jarvis.bat. That's it.

On Windows (ZIP download):

1. Unzip the folder.
2. **Double-click `Start Jarvis.bat`.**
3. First run creates `.venv`, installs core + voice packages, copies `.env.example` → `.env` if needed, then opens the HUD.
4. Later runs skip reinstall unless packages are missing.

If Python is missing, the bat stops with plain English steps (install from python.org with **Add to PATH** and **tcl/tk**). Mic problems only warn — the window still opens and **typing works**.

Optional: put `OPENAI_API_KEY=...` in `.env` for free-form chat (not required for builtins / skills / PC actions).

Your saved lessons live in `%USERPROFILE%\.jarvis\` so they survive updates.

## Desktop window

The HUD shows a cyan orb on a dark grid, a one-line caption, and a text bar + Hold demo. Built-ins work without teaching: `hi`, `help`, `what time is it`.

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

Speech prefers free Windows British male TTS (*George* / `en-GB`) when available. Soft tip: install the English (United Kingdom) speech pack in Windows Settings → Time & Language → Speech.

Jarvis listens after you say its name (`Jarvis` by default), or tap **Listen** on the HUD for one command without the wake word. Use **Mute** to silence the mic. Typed replies are spoken aloud. Typing always works if the mic fails.

Say `diagnose` or `test mic`, or use **Test mic** on the HUD.

## Safety

- Allowlisted apps / folder roots / https URLs only
- No free-form shell, delete, or `file://` / `javascript:` URLs
- Medium-risk actions need a `yes` confirm

## Config

See `config.yaml`. Copy `.env.example` to `.env` for optional OpenAI (`JARVIS_CLOUD_CHAT=0` forces offline chat).

## Plex library import (local files only)

Jarvis will **not** download movies from the web. It can copy/move files you already have into your Plex Movies folder. Set `plex.library_dir` in `config.yaml`, keep sources under allowlisted roots, then `add ~/Downloads/MyMovie.mp4 to plex` → `yes` → `scan plex`.

## Advanced

- **One-file exe:** run `scripts\Build-Exe.bat`, then double-click `dist\Jarvis.exe` (optional `.env` beside the exe). No bat/venv needed at runtime.
- **PowerShell setup:** `scripts\setup.ps1` (or `-SkipMic`) for advanced troubleshooting. Beginners should use `Start Jarvis.bat` only.
- **Dev:** `python -m venv .venv` → activate → `pip install -r requirements.txt` → `pytest -q` → `python -m assistant gui`

**Before every push:** `python scripts/preflight.py` must print `PREFLIGHT PASSED`.
