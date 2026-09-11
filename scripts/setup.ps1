#Requires -Version 5.1
# Advanced setup (optional). Beginners: double-click Start Jarvis.bat at the repo root.
param(
  [switch]$SkipMic
)
$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location -Path $RepoRoot

function Fail([string]$Reason) {
  Write-Host "Setup stopped: $Reason"
  exit 1
}

Write-Host "Jarvis advanced setup (repo root: $RepoRoot)..."
Write-Host "Tip: beginners can ignore this script and use Start Jarvis.bat instead."

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  Fail "Python not found. Install from python.org and tick Add to PATH and tcl/tk."
}

if (-not (Test-Path ".venv")) {
  Write-Host "Creating .venv..."
  python -m venv .venv
  if ($LASTEXITCODE -ne 0) { Fail "venv create failed." }
}

$py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$pip = Join-Path $RepoRoot ".venv\Scripts\pip.exe"
if (-not (Test-Path $py)) { Fail "venv python missing." }

Write-Host "Installing core packages..."
& $pip install -U pip
& $pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { Fail "pip install requirements.txt failed." }

Write-Host "Installing voice packages (sounddevice wheels - no pipwin)..."
& $pip install -r requirements-voice.txt
if ($LASTEXITCODE -ne 0) { Fail "pip install requirements-voice.txt failed." }

if (-not (Test-Path ".env")) {
  if (Test-Path ".env.example") {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example - add OPENAI_API_KEY for free-form chat."
  }
}

Write-Host "Checking imports..."
& $py -c "import assistant, yaml, sounddevice, speech_recognition, pyttsx3; print('core+voice ok')"
if ($LASTEXITCODE -ne 0) { Fail "import check failed - voice packages not installed." }

# Stamp so Start Jarvis.bat skips reinstall next time
Set-Content -Path (Join-Path $RepoRoot ".venv\.jarvis_deps_ok") -Value "ok" -Encoding ASCII

Write-Host "UK TTS tip: install English (United Kingdom) speech pack in Windows Settings for a George-style voice."

if ($SkipMic) {
  Write-Host "Skipping microphone check (-SkipMic)."
  Write-Host "Setup finished. Run Start Jarvis.bat"
  exit 0
}

Write-Host "Probing microphone (soft — will not block; typing always works)..."
$probe = Join-Path $RepoRoot "_mic_probe_tmp.py"
@(
  "from assistant.voice.mic_health import probe_microphone, mark_probed"
  "r = probe_microphone()"
  "mark_probed(status=r.status.value)"
  "print(r.status.value)"
  "print(r.message)"
  "raise SystemExit(0)"
) | Set-Content -Path $probe -Encoding ASCII

& $py $probe
Remove-Item $probe -ErrorAction SilentlyContinue

Write-Host "Setup finished. Run Start Jarvis.bat (GUI opens even if mic failed)."
exit 0
