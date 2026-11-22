#!/usr/bin/env bash
# Thin CLI wrapper for the auto-brain advisor.
# Sets PYTHONPATH to the installed package location, then delegates to the advisor.
# Used by the /auto-brain skill and can be called directly.
export PYTHONPATH="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/smartmodel/lib${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m auto_brain.advisor "$@"
