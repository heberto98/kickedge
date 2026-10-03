@echo off
rem KickEdge local launcher: double-click to start, Ctrl+C in this window to stop.
rem No admin rights, services, registry or startup entries are used.
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo KickEdge environment not found: .venv\Scripts\python.exe
  echo Create it once from this folder:
  echo    python -m venv .venv
  echo    .venv\Scripts\python.exe -m pip install -r requirements.lock.txt
  pause
  exit /b 1
)
echo Starting KickEdge at http://127.0.0.1:8000 - the browser opens when it is ready.
echo Press Ctrl+C to stop KickEdge.
".venv\Scripts\python.exe" -m kickedge.web --open
pause
