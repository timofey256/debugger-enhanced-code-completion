#!/usr/bin/env bash
set -euo pipefail

PKG_DIR="backend"

cd "$PKG_DIR"

echo "Cleaning old build artifacts..."
rm -rf dist/ build/ *.egg-info

echo "Building package..."
python -m build

echo "Build complete. Generated files:"
ls -lh dist/

read -p "Do you want to upload these to PyPI? [y/N] " choice
case "$choice" in
  y|Y )
    echo "Uploading to PyPI..."
    twine upload dist/*
    ;;
  * )
    echo "Upload skipped."
    ;;
esac
