#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
BACKEND_DIR="$PROJECT_DIR/backend"
EXAMPLE_DIR="$PROJECT_DIR/example/jsonschema"

if [ ! -d "$VENV_DIR" ]; then
  echo ">>> Creating virtual environment in $VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi

echo ">>> Activating venv"
source "$VENV_DIR/bin/activate"

echo ">>> Upgrading pip"
pip install --upgrade pip

echo ">>> Installing backend package (editable)"
pip install --force-reinstall -e "$BACKEND_DIR"

echo ">>> Installing runtime dependencies"
pip install --force-reinstall --ignore-installed flask requests

export PORT=5123

echo ">>> Starting server on port $PORT"
exec pytest-smart-debugger-server "$EXAMPLE_DIR"
