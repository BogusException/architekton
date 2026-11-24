#!/usr/bin/env bash
# Tear down the development environment created by dev-install.sh.
# Removes .venv, build artifacts, and compiled bytecode.
# Does NOT uninstall architekton from the system -- use scripts/uninstall.sh for that.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Removing dev environment ==="

if [[ -d "$SCRIPT_DIR/.venv" ]]; then
    rm -rf "$SCRIPT_DIR/.venv"
    echo "  removed .venv"
else
    echo "  .venv not present, skipping"
fi

find "$SCRIPT_DIR" -maxdepth 3 -name "*.egg-info" -type d | while read -r d; do
    rm -rf "$d"
    echo "  removed $d"
done

find "$SCRIPT_DIR/src" "$SCRIPT_DIR/tests" -name "__pycache__" -type d 2>/dev/null | while read -r d; do
    rm -rf "$d"
    echo "  removed $d"
done

echo ""
echo "Done. To reinstall the dev environment, run: bash dev-install.sh"
echo "To uninstall architekton from the system, run: bash scripts/uninstall.sh"
