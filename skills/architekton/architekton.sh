#!/usr/bin/env bash
# Thin CLI wrapper for the architekton advisor.
# Sets PYTHONPATH to the installed package location, then delegates to the advisor.
# Used by the /architekton skill and can be called directly.
export PYTHONPATH="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/architekton/lib${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m architekton.advisor "$@"
