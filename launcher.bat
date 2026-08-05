@echo off
REM Double-click launcher for the Biosensor viewer (Windows).
REM Creates the venv on first run, installs the package, then starts the
REM Flask viewer and opens it in the default browser.

cd /d "%~dp0"

if not exist ".venv" (
  echo Setting up virtual environment ^(first run only^)...
  python -m venv .venv
  call .venv\Scripts\activate.bat
  pip install -q --upgrade pip
  pip install -q -e ".[dev]"
) else (
  call .venv\Scripts\activate.bat
)

start "" /b cmd /c "timeout /t 1 >nul & start http://127.0.0.1:5050"

python viewer\app.py
