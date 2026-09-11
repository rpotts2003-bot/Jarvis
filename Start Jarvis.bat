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
python -m assistant chat
pause
