#!/usr/bin/env bash
# Set up the development environment.
# Safe to run multiple times. Run this once after cloning, and again
# whenever pyproject.toml changes.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$REPO/.venv"
PYTHON="${PYTHON:-python3}"

# 1. Create venv if missing.
if [[ ! -f "$VENV/bin/python" ]]; then
    echo "Creating virtualenv at $VENV ..."
    "$PYTHON" -m venv "$VENV"
fi

# Always use the venv's own pip -- never whatever pip is on PATH.
PIP="$VENV/bin/pip"

echo "Installing architekton in editable mode (with dev dependencies) ..."
"$PIP" install -e "$REPO[dev]" --quiet

# 2. Git private-path guard.
# Sets core.hooksPath so pre-commit and pre-push reject accidental commits
# of private paths. Only needed once per clone; safe to repeat.
if git -C "$REPO" config core.hooksPath >/dev/null 2>&1 && \
   [[ "$(git -C "$REPO" config core.hooksPath)" == ".githooks" ]]; then
    echo "git hooks: already set to .githooks"
else
    git -C "$REPO" config core.hooksPath .githooks
    echo "git hooks: set core.hooksPath to .githooks"
fi

# 3. Contributor-only Claude Code hooks.
# settings.local.json is git-ignored and loaded by Claude Code on top of
# settings.json. It carries the Stop and PostToolUse hooks that require the
# project venv (save-response, auto-commit, auto-test, format-on-save).
LOCAL_SETTINGS="$REPO/.claude/settings.local.json"
HOOK_DIR="\$CLAUDE_PROJECT_DIR/.claude/hooks"

python3 -c "
import json, os, sys
p = sys.argv[1]
hook_dir = sys.argv[2]
settings = {
    'hooks': {
        'PostToolUse': [
            {
                'matcher': 'Edit|Write',
                'hooks': [
                    {'type': 'command', 'command': hook_dir + '/auto-test.sh',      'timeout': 30, 'statusMessage': 'Running tests...'},
                    {'type': 'command', 'command': hook_dir + '/format-on-save.sh', 'timeout': 10, 'statusMessage': 'Formatting...'}
                ]
            }
        ],
        'Notification': [
            {
                'matcher': '',
                'hooks': [
                    {'type': 'command', 'command': hook_dir + '/notify.sh', 'timeout': 10}
                ]
            }
        ],
        'Stop': [
            {
                'matcher': '',
                'hooks': [
                    {'type': 'command', 'command': hook_dir + '/save-response.sh',  'timeout': 30, 'statusMessage': 'Saving response...'},
                    {'type': 'command', 'command': hook_dir + '/auto-commit.sh',    'timeout': 30, 'statusMessage': 'Auto-committing changes...'}
                ]
            }
        ]
    }
}
with open(p, 'w') as f:
    json.dump(settings, f, indent=2)
    f.write('\n')
" "$LOCAL_SETTINGS" "$HOOK_DIR"
echo "wrote $LOCAL_SETTINGS (contributor hooks)"

echo ""
echo "Done. Next steps:"
echo "  dev-configure.sh   open the interactive config editor"
echo "  dev-run.sh         show current config and detected session model"
echo "  dev-test.sh        run the full test suite"
echo "  dev-uninstall.sh   remove the dev environment"
echo ""
echo "To install architekton system-wide: bash scripts/install.sh"
