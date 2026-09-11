@echo off
setlocal EnableExtensions
title Build Jarvis.exe
cd /d "%~dp0"

echo === Jarvis Windows one-file build ===

where python >nul 2>&1
if errorlevel 1 (
  echo Build stopped: Python not found. Install from python.org ^(Add to PATH + tcl/tk^).
  exit /b 1
)

if not exist .venv (
  echo Creating .venv...
  python -m venv .venv
  if errorlevel 1 (
    echo Build stopped: could not create venv.
    exit /b 1
  )
)
call .venv\Scripts\activate
if errorlevel 1 (
  echo Build stopped: could not activate venv.
  exit /b 1
)

echo Installing core + build deps...
python -m pip install -U pip
if errorlevel 1 (
  echo Build stopped: pip upgrade failed.
  exit /b 1
)
pip install -r requirements.txt -r requirements-build.txt
if errorlevel 1 (
  echo Build stopped: core pip install failed.
  exit /b 1
)

echo Installing voice deps (sounddevice wheels - no pipwin)...
pip install -r requirements-voice.txt
if errorlevel 1 (
  echo Build stopped: voice packages failed.
  exit /b 1
)

echo Running preflight...
python scripts\preflight.py
if errorlevel 1 (
  echo Build stopped: preflight failed.
  exit /b 1
)

echo Freezing with PyInstaller...
python -m PyInstaller --noconfirm jarvis.spec
if errorlevel 1 (
  echo Build stopped: PyInstaller failed.
  exit /b 1
)

if not exist dist\Jarvis.exe (
  echo Build stopped: dist\Jarvis.exe was not created.
  exit /b 1
)

copy /Y .env.example dist\.env.example >nul
if errorlevel 1 (
  echo Build stopped: could not copy .env.example beside the exe.
  exit /b 1
)
if not exist dist\.env.example (
  echo Build stopped: dist\.env.example missing.
  exit /b 1
)
if exist VERSION copy /Y VERSION dist\VERSION >nul

echo Running post-build smoke against dist\Jarvis.exe...
python scripts\smoke_exe.py --exe dist\Jarvis.exe
if errorlevel 1 (
  echo Build stopped: smoke failed against the frozen exe.
  exit /b 1
)

echo %CD%\dist\Jarvis.exe
echo Build OK.
exit /b 0
