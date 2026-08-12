#!/bin/bash
# Double-click launcher for the Biosensor viewer (macOS).
# Creates (or repairs) the venv on first run, installs the package, then
# starts the Flask viewer and opens it in the default browser.

cd "$(dirname "$0")" || exit 1

PY=".venv/bin/python"

# Rebuild the venv if it's missing or incomplete: a partial editable install
# leaves an interpreter that can't import the package.
if [ ! -x "$PY" ] || ! "$PY" -c "import biosensor" 2>/dev/null; then
  echo "Setting up virtual environment (first run only)..."
  python3 -m venv .venv
  # If this project happens to live in a Dropbox folder, stop the venv's
  # compiled binaries from syncing: sync churn re-signs the .so files and
  # macOS then refuses to load them mid-session. A no-op outside Dropbox, so
  # it's safe to run for everyone. Set before installing any compiled dep.
  xattr -w com.dropbox.ignored 1 .venv 2>/dev/null || true
  "$PY" -m ensurepip --upgrade
  "$PY" -m pip install -q --upgrade pip
  "$PY" -m pip install -q -e ".[dev]"
fi

( sleep 1 && open "http://127.0.0.1:5050" ) &

exec "$PY" viewer/app.py
