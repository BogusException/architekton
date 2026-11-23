#!/usr/bin/env bash
# Show current architekton config and detected session model.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
source .venv/bin/activate
exec python -m architekton.advisor status "$@"
