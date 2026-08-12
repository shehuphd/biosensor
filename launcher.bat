@echo off
REM Double-click launcher for the Biosensor viewer (Windows).
REM Creates (or repairs) the venv on first run, installs the package, then
REM starts the Flask viewer and opens it in the default browser.

cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"

REM Rebuild the venv if it's missing or incomplete: a partial editable install
REM leaves an interpreter that can't import the package.
if not exist "%PY%" goto setup
"%PY%" -c "import biosensor" 2>nul
if errorlevel 1 goto setup
goto run

:setup
echo Setting up virtual environment ^(first run only^)...
python -m venv .venv
"%PY%" -m ensurepip --upgrade
"%PY%" -m pip install -q --upgrade pip
"%PY%" -m pip install -q -e ".[dev]"

:run
start "" /b cmd /c "timeout /t 1 >nul & start http://127.0.0.1:5050"
"%PY%" viewer\app.py
