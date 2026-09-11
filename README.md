# Jarvis (desktop MVP)

Local-first desktop assistant brain: **push-to-talk ready state machine**, **teachable memory**, **allowlisted PC actions**, and a **listening orb model** (Idle / Listening / Thinking / Speaking).

> This MVP runs fully offline for intent + memory + action policy. Real Whisper STT / Windows SAPI TTS adapters are stubbed behind interfaces — wire them on your Windows PC when you are ready for mic/speakers.

## Quick start

```bash
cd Jarvis
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest -q
python -m assistant scenarios
python -m assistant chat
```

## Desktop window

`Start Jarvis.bat` (or `python -m assistant gui`) opens a **HUD-style window**:
- large cyan concentric orb on a dark grid (Idle / Listening / Thinking / Speaking animations)
- one-line caption for the last reply (no chat wall)
- tiny text bar at the bottom + **Hold** demo for the listen/speak glow

Talk by typing in the bar for now (mic/TTS on Windows comes next). Built-ins work without teaching: `hi`, `help`, `what time is it`. Free-form chat needs `OPENAI_API_KEY` in the environment; skills, Plex, and allowlisted actions still work offline.

## Easiest way to run (Windows)

**Option A — one `.exe` (best if you’re new)**  
After GitHub Actions finishes on `main`, download **Jarvis-windows** from the repo’s Actions → Artifacts (or Releases), then double-click `Jarvis.exe`.

**Option B — no build tools**  
Double-click `Start Jarvis.bat` in this folder (needs Python installed once from python.org).

Your saved lessons live in `%USERPROFILE%\.jarvis\` so they survive updates.

## Teach it

```
> learn when I say morning do open calculator
Got it — learn "morning" → open calculator? Say yes to save.
> yes
Got it — saved.
> morning
Opened calculator
> list skills
Skills I know:
- say "morning" → open calculator
```

Also works: `next time I say downloads, do open chrome` · `remember that my name is R.P.`

## Safety

- Allowlisted apps / folder roots / https URLs only
- No free-form shell, delete, or `file://` / `javascript:` URLs
- Medium-risk actions need a `yes` confirm
- Every attempt is audit-logged when `~/.jarvis/audit.jsonl` is used from the chat CLI

## Config

See `config.yaml` for apps, folder roots, and timeouts.

## Tests

`pytest` covers memory, router, voice state machine, and orchestrator confirm gates.  
`python -m assistant scenarios` runs the reliability scenario pack (must be all PASS).

**Before every push:** `python scripts/preflight.py` (self-method AST check + pytest + scenarios + compileall). Must print `PREFLIGHT PASSED`.


## Plex library import (local files only)

Jarvis will **not** download movies from the web. It can copy/move files you already have into your Plex Movies folder.

1. Install [Plex Media Server](https://www.plex.tv/media-server-downloads/) on your laptop.
2. Create a folder e.g. `C:\PlexMedia\Movies` and add it as a Movies library in Plex.
3. Set `plex.library_dir` in `config.yaml` to that folder.
4. Keep your source files under an allowlisted root (`~/Downloads`, `~/Documents`, etc.).
5. In chat:

```
> add ~/Downloads/MyMovie.mp4 to plex
Confirm copy MyMovie.mp4 into Plex library?
> yes
> scan plex
```


## Voice (always listening)

Speech uses **free Windows British male TTS** when available (prefers *George* / `en-GB` male), with a calmer rate (~145) so it feels more like MCU Jarvis’s *manner* — not a celebrity voice clone. Tune in `config.yaml` under `voice:` or `JARVIS_TTS_RATE` / `JARVIS_TTS_VOICE` in `.env`.


Jarvis listens in the background and **only responds after you say its name** (`Jarvis` by default). Use the **Mute** button on the HUD to silence the mic.

1. Run `Setup Voice.bat` once (installs mic/TTS packages; PyAudio can be fiddly on Windows).
2. Allow mic access if Windows asks.
3. Say: `Jarvis, what time is it?`

Typing still works if the mic packages are missing.

Mute is app-level (stops wake/STT feed) and persists in `%USERPROFILE%\.jarvis\ui_prefs.json`. Windows mic privacy / OS mute shows an error on the HUD instead of failing silently.


## OpenAI free-form chat

Built-ins and PC actions work offline. For free-form conversation:

1. Copy `.env.example` to `.env` (Start Jarvis.bat does this once).
2. Put your key in `OPENAI_API_KEY=...`
3. Restart Jarvis — status should show `chat:OpenAI`.

Set `JARVIS_CLOUD_CHAT=0` to force offline chat replies even if a key is present.
