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
