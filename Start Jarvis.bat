@echo off
setlocal EnableExtensions EnableDelayedExpansion
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

REM Bundled local LLM (llama-cpp-python). Prefer prebuilt CPU wheel — never silent source build first.
if not exist .venv\.jarvis_local_llm_ok (
  echo Installing local brain runtime ^(llama-cpp-python, CPU^)...
  echo Using prebuilt CPU wheel...
  set "LLAMA_OK=0"
  pip install "llama-cpp-python" --only-binary=:all: --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
  if not errorlevel 1 set "LLAMA_OK=1"
  if "!LLAMA_OK!"=="0" (
    echo Prebuilt-only install failed. Retrying once with extra-index-url ^(still prefers wheel^)...
    pip install "llama-cpp-python" --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
    if not errorlevel 1 set "LLAMA_OK=1"
  )
  if "!LLAMA_OK!"=="0" (
    echo.
    echo Could not install llama-cpp-python on this PC.
    echo Free-form chat needs that package OR an optional cloud key.
    echo Built-ins ^(hi / help / time^) still work. Typing still works.
    echo Try: pip install "llama-cpp-python" --only-binary=:all: --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
    echo Or set JARVIS_DISABLE_LOCAL_LLM=1 in .env to silence download attempts.
    echo.
  ) else (
    python -c "import llama_cpp; print('llama-cpp ok')" >nul 2>&1
    if errorlevel 1 (
      echo llama-cpp-python imported poorly — free-form chat may be unavailable.
    ) else (
      echo ok> .venv\.jarvis_local_llm_ok
      echo Local brain runtime ready.
    )
  )
)

if not exist .env if exist .env.example (
  copy /Y .env.example .env >nul
  echo Created .env — first chat may download Jarvis's brain ^(~1 GB^) once.
)

echo Checking microphone ^(typing still works if this fails^)...
python -c "from assistant.voice.mic_health import probe_microphone, mark_probed; r=probe_microphone(); mark_probed(status=r.status.value); print(r.message); raise SystemExit(0)"
if errorlevel 1 (
  echo Mic probe skipped or unavailable — you can still type in the window.
)

echo Tip: neural UK male voice ^(Ryan^) needs internet; offline falls back to Windows SAPI.
echo Tip: No Ollama required. First chat may download ~1 GB brain into %%USERPROFILE%%\.jarvis\models\
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
