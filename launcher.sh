#!/bin/bash
# Double-click / terminal launcher for the Biosensor viewer (Linux).
# Creates (or repairs) the venv on first run, installs the package, then
# starts the Flask viewer and opens it in the default browser.

cd "$(dirname "$0")" || exit 1

PY=".venv/bin/python"

# Rebuild the venv if it's missing or incomplete: a partial editable install
# leaves an interpreter that can't import the package.
if [ ! -x "$PY" ] || ! "$PY" -c "import biosensor" 2>/dev/null; then
  echo "Setting up virtual environment (first run only)..."
  python3 -m venv .venv
  "$PY" -m ensurepip --upgrade
  "$PY" -m pip install -q --upgrade pip
  "$PY" -m pip install -q -e ".[dev]"
fi

( sleep 1 && xdg-open "http://127.0.0.1:5050" >/dev/null 2>&1 ) &

exec "$PY" viewer/app.py
