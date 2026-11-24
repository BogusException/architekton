#!/usr/bin/env bash
# Launch the interactive config editor.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
[[ -f .venv/bin/activate ]] || { echo "Run dev-install.sh first to set up the dev environment."; exit 1; }
source .venv/bin/activate
exec python -m architekton.advisor configure "$@"
