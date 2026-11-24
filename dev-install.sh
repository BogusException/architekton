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
echo "Done. Next steps:"
echo "  dev-configure.sh   open the interactive config editor"
echo "  dev-run.sh         show current config and detected session model"
echo "  dev-test.sh        run the full test suite"
echo "  dev-uninstall.sh   remove the dev environment"
echo ""
echo "To install architekton on your system: bash scripts/install.sh"
