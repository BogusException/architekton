#!/usr/bin/env bash
# UserPromptSubmit hook: warns when prompt complexity does not match the session model.
# Reads the hook JSON on stdin. Silent on match, on disable, and on any failure.

BRAIN_HOME="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/architekton"
export PYTHONPATH="$BRAIN_HOME/lib${PYTHONPATH:+:$PYTHONPATH}"
python3 -m architekton.advisor warn || true
exit 0
