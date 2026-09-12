@echo off
setlocal EnableExtensions
title Jarvis
cd /d "%~dp0"

echo === Jarvis ===

where python >nul 2>&1
if errorlevel 1 (
  echo.
  echo Python was not found.
  echo Install Python from https://www.python.org/downloads/
  echo Tick "Add python.exe to PATH" and "tcl/tk and IDLE".
  echo Then double-click Start Jarvis.bat again.
  echo.
  pause
  exit /b 1
)

if not exist .venv (
  echo First run: creating .venv...
  python -m venv .venv
  if errorlevel 1 (
    echo Could not create .venv. Is Python installed correctly?
    pause
    exit /b 1
  )
)

call .venv\Scripts\activate
if errorlevel 1 (
  echo Could not activate .venv.
  pause
  exit /b 1
)

set "NEED_INSTALL=0"
if not exist .venv\.jarvis_deps_ok set "NEED_INSTALL=1"
if "%NEED_INSTALL%"=="0" (
  python -c "import assistant, yaml, sounddevice, speech_recognition, pyttsx3, edge_tts" >nul 2>&1
  if errorlevel 1 set "NEED_INSTALL=1"
)

if "%NEED_INSTALL%"=="1" (
  echo Installing packages ^(first run or deps changed^)...
  python -m pip install -U pip
  if errorlevel 1 (
    echo pip upgrade failed.
    pause
    exit /b 1
  )
  pip install -r requirements.txt -r requirements-voice.txt
  if errorlevel 1 (
    echo Package install failed. Check your internet connection and try again.
    pause
    exit /b 1
  )
  python -c "import assistant, yaml, sounddevice, speech_recognition, pyttsx3, edge_tts; print('deps ok')"
  if errorlevel 1 (
    echo Import check failed after install.
    pause
    exit /b 1
  )
  echo ok> .venv\.jarvis_deps_ok
  echo Packages ready.
)

if not exist .env if exist .env.example (
  copy /Y .env.example .env >nul
  echo Created .env — add OPENAI_API_KEY there for free-form chat.
)

echo Checking microphone ^(typing still works if this fails^)...
python -c "from assistant.voice.mic_health import probe_microphone, mark_probed; r=probe_microphone(); mark_probed(status=r.status.value); print(r.message); raise SystemExit(0)"
if errorlevel 1 (
  echo Mic probe skipped or unavailable — you can still type in the window.
)

echo Tip: neural UK male voice ^(Ryan^) needs internet; offline falls back to Windows SAPI.
echo Starting Jarvis window...
python -m assistant gui
if errorlevel 1 (
  echo.
  echo Jarvis closed with an error.
  echo If you saw a tkinter / tcl error, reinstall Python from python.org and tick "tcl/tk and IDLE".
  echo Voice packages install automatically on the next Start Jarvis.bat run.
  echo.
  pause
)
endlocal
