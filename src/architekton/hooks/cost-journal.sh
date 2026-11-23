#!/usr/bin/env bash
# Stop hook: appends one session record to the cost journal.
# Silent on any error so it never blocks post-session cleanup.

BRAIN_HOME="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/architekton"
export PYTHONPATH="$BRAIN_HOME/lib${PYTHONPATH:+:$PYTHONPATH}"
python3 -m architekton.advisor session-end || true
exit 0
