@echo off
setlocal
title Build Jarvis.exe
cd /d "%~dp0"
echo === Jarvis Windows one-file build ===

where python >nul 2>&1
if errorlevel 1 (
  echo BUILD FAILED: Python not found. Install from python.org ^(Add to PATH + tcl/tk^).
  pause
  exit /b 1
)

if not exist .venv (
  echo Creating .venv...
  python -m venv .venv
  if errorlevel 1 (
    echo BUILD FAILED: could not create venv
    pause
    exit /b 1
  )
)
call .venv\Scripts\activate

echo Installing core + build deps...
python -m pip install -U pip
pip install -r requirements.txt -r requirements-build.txt
if errorlevel 1 (
  echo BUILD FAILED: core pip install
  pause
  exit /b 1
)

echo Installing voice deps ^(needed inside the exe^)...
pip install -r requirements-voice.txt
if errorlevel 1 (
  echo WARNING: voice pip failed. Trying pipwin for PyAudio...
  pip install pipwin
  pipwin install pyaudio
)

echo Running preflight...
python scripts\preflight.py
if errorlevel 1 (
  echo BUILD FAILED: preflight
  pause
  exit /b 1
)

echo Freezing with PyInstaller...
python -m PyInstaller --noconfirm jarvis.spec
if errorlevel 1 (
  echo BUILD FAILED: PyInstaller
  pause
  exit /b 1
)

if not exist dist\Jarvis.exe (
  echo BUILD FAILED: dist\Jarvis.exe missing
  pause
  exit /b 1
)

if exist .env.example copy /Y .env.example dist\.env.example >nul
if exist VERSION copy /Y VERSION dist\VERSION >nul

echo Running post-build smoke ^(diagnose^)...
python scripts\smoke_exe.py --exe dist\Jarvis.exe
set SMOKE=%ERRORLEVEL%
if not "%SMOKE%"=="0" (
  echo.
  echo BUILD WARNING: smoke did not fully pass ^(exit %SMOKE%^).
  echo Exe is at dist\Jarvis.exe — test it manually. Mic may need Windows privacy allow.
)

echo.
echo ========================================
echo  Jarvis.exe ready:
echo  %CD%\dist\Jarvis.exe
echo ========================================
echo Optional: copy .env.example to dist\.env and add OPENAI_API_KEY=
explorer dist
pause
endlocal
