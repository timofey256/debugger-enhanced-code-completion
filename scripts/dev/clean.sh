#!/usr/bin/env bash
set -euo pipefail

echo "Cleaning repository build artifacts..."

# Root
find . -name '__pycache__' -type d -exec rm -rf {} +
find . -name '*.pyc' -delete

# Python backend
rm -rf backend/build/
rm -rf backend/dist/
rm -rf backend/src/*.egg-info/
rm -rf backend/.pytest_cache/
rm -rf backend/.mypy_cache/
rm -rf backend/.coverage

# VSCode extension
rm -rf pytest-smart-debugger-extension/out/
rm -rf pytest-smart-debugger-extension/node_modules/
rm -rf pytest-smart-debugger-extension/dist/

echo "Cleanup complete."
