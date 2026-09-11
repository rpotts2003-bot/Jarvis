@echo off
title Jarvis
cd /d "%~dp0"
if not exist .venv (
  echo First run: setting up...
  python -m venv .venv
  call .venv\Scripts\activate
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate
)
if not exist .env if exist .env.example (
  copy /Y .env.example .env >nul
  echo Created .env — add OPENAI_API_KEY there for free-form chat.
)
echo Starting Jarvis window...
python -m assistant gui
if errorlevel 1 (
  echo.
  echo If you saw a tkinter error, reinstall Python from python.org and tick "tcl/tk".
  echo For mic listening, run Setup Voice.bat once.
  pause
)
