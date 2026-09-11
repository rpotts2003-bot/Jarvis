#Requires -Version 5.1
param(
  [switch]$SkipMic
)
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Fail([string]$Reason) {
  Write-Host "Setup stopped: $Reason"
  exit 1
}

Write-Host "Jarvis setup starting..."

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  Fail "Python not found. Install from python.org and tick Add to PATH and tcl/tk."
}

if (-not (Test-Path ".venv")) {
  Write-Host "Creating .venv..."
  python -m venv .venv
  if ($LASTEXITCODE -ne 0) { Fail "venv create failed." }
}

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$pip = Join-Path $PSScriptRoot ".venv\Scripts\pip.exe"
if (-not (Test-Path $py)) { Fail "venv python missing." }

Write-Host "Installing core packages..."
& $pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { Fail "pip install requirements.txt failed." }

Write-Host "Installing voice packages..."
& $pip install -r requirements-voice.txt
if ($LASTEXITCODE -ne 0) {
  Write-Host "Voice pip had errors - trying pipwin for PyAudio..."
  & $pip install pipwin
  $pipwin = Join-Path $PSScriptRoot ".venv\Scripts\pipwin.exe"
  if (Test-Path $pipwin) {
    & $pipwin install pyaudio
  }
}

if (-not (Test-Path ".env")) {
  if (Test-Path ".env.example") {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example - add OPENAI_API_KEY for free-form chat."
  }
}

Write-Host "Checking imports..."
& $py -c "import assistant; import yaml; print('core ok')"
if ($LASTEXITCODE -ne 0) { Fail "core import failed." }

Write-Host "UK TTS tip: install English (United Kingdom) speech pack in Windows Settings for a George-style voice."

if ($SkipMic) {
  Write-Host "Skipping microphone check (-SkipMic)."
  Write-Host "Setup finished (mic skipped)."
  exit 0
}

Write-Host "Probing microphone..."
$probe = Join-Path $PSScriptRoot "_mic_probe_tmp.py"
@(
  "from assistant.voice.mic_health import probe_microphone, mark_probed"
  "r = probe_microphone()"
  "mark_probed(status=r.status.value)"
  "print(r.status.value)"
  "print(r.message)"
  "raise SystemExit(0 if r.ok else 2)"
) | Set-Content -Path $probe -Encoding ASCII

& $py $probe
$code = $LASTEXITCODE
Remove-Item $probe -ErrorAction SilentlyContinue

if ($code -eq 0) {
  Write-Host "Microphone OK."
  Write-Host "Setup finished. Run Start Jarvis.bat"
  exit 0
}

$status = "unknown"
try {
  $status = & $py -c "from assistant.voice.mic_health import probe_microphone; print(probe_microphone().status.value)"
} catch {
  $status = "error"
}
Fail "microphone check failed ($status). Fix that, re-run, or use -SkipMic."
