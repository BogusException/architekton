#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
[[ -f .venv/bin/python ]] || { echo "Run dev-install.sh first to set up the dev environment."; exit 1; }
export PYTHONPATH="$SCRIPT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
exec .venv/bin/python -m unittest discover -s tests -v "$@"
