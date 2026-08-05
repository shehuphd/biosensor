#!/bin/bash
# Double-click / terminal launcher for the Biosensor viewer (Linux).
# Creates the venv on first run, installs the package, then starts the
# Flask viewer and opens it in the default browser.

cd "$(dirname "$0")" || exit 1

if [ ! -d ".venv" ]; then
  echo "Setting up virtual environment (first run only)..."
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -q --upgrade pip
  pip install -q -e ".[dev]"
else
  source .venv/bin/activate
fi

( sleep 1 && xdg-open "http://127.0.0.1:5050" >/dev/null 2>&1 ) &

python viewer/app.py
