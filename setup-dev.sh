#!/usr/bin/env bash
# Set up the development environment.
# Safe to run multiple times. Run this once after cloning, and again
# whenever pyproject.toml changes.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$REPO/.venv"
PYTHON="${PYTHON:-python3}"

# Create venv if missing
if [[ ! -f "$VENV/bin/python" ]]; then
    echo "Creating virtualenv at $VENV ..."
    "$PYTHON" -m venv "$VENV"
fi

# Always use the venv's own pip -- never whatever pip is on PATH
PIP="$VENV/bin/pip"

echo "Installing architekton in editable mode ..."
"$PIP" install -e "$REPO" --quiet

echo ""
echo "Done. To use:"
echo "  source $VENV/bin/activate"
echo "  python -m architekton.advisor --help"
