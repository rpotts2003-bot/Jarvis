@echo off
title Build Jarvis.exe
cd /d "%~dp0"
echo Building Jarvis.exe (one-file, no console)...
if not exist .venv (
  python -m venv .venv
)
call .venv\Scripts\activate
pip install -r requirements.txt -r requirements-build.txt
pip install -r requirements-voice.txt
if errorlevel 1 (
  echo Voice deps failed — building core GUI exe anyway.
)
python -m PyInstaller --noconfirm jarvis.spec
if errorlevel 1 (
  echo BUILD FAILED
  pause
  exit /b 1
)
echo.
echo OK: dist\Jarvis.exe
echo Copy that file anywhere. First run may need Windows mic permission.
echo Optional: put a .env next to Jarvis.exe with OPENAI_API_KEY=...
explorer dist
pause
