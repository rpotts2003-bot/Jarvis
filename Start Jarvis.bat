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
echo Starting Jarvis window...
python -m assistant gui
if errorlevel 1 (
  echo.
  echo If you saw a tkinter error, reinstall Python from python.org and tick "tcl/tk".
  pause
)
