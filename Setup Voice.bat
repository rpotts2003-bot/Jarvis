@echo off
title Jarvis voice setup
cd /d "%~dp0"
if not exist .venv (
  python -m venv .venv
)
call .venv\Scripts\activate
echo Installing voice packages...
pip install -r requirements-voice.txt
if errorlevel 1 (
  echo.
  echo If PyAudio failed, try: pip install pipwin ^&^& pipwin install pyaudio
  pause
)
echo.
echo Optional: copy .env.example to .env and paste your OPENAI_API_KEY for free-form chat.
echo Then run Start Jarvis.bat
pause
