#!/bin/bash
# macOS / Linux launcher. Double-click (macOS) or run ./start.command
cd "$(dirname "$0")" || exit 1

PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  echo "Python 3.10+ is required. Install it from https://www.python.org/downloads/ and run this again."
  read -r -p "Press Enter to close."
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "First-time setup: creating environment... (1-3 minutes)"
  "$PY" -m venv .venv || exit 1
  rm -f .venv/.installed
fi
if [ ! -f ".venv/.installed" ]; then
  echo "Installing packages..."
  .venv/bin/python -m pip install --upgrade pip -q
  .venv/bin/python -m pip install -r requirements.txt -q || { echo "Install failed."; exit 1; }
  touch .venv/.installed
fi

exec .venv/bin/python app.py
