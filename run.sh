#!/usr/bin/env bash
# Show current auto-brain config and detected session model.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
source .venv/bin/activate
exec python -m auto_brain.advisor status "$@"
