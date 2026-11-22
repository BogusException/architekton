#!/usr/bin/env bash
# Installs auto-brain: package + hook into ~/.claude/smartmodel, wrapper into ~/bin/claude,
# hook registration in ~/.claude/settings.json. Safe to re-run.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
BRAIN_HOME="$CLAUDE_DIR/smartmodel"
BIN_DIR="${AUTO_BRAIN_BIN_DIR:-$HOME/bin}"
WRAPPER="$BIN_DIR/claude"
HOOK="$BRAIN_HOME/lib/auto_brain/hooks/smartmodel-warn.sh"
JOURNAL_HOOK="$BRAIN_HOME/lib/auto_brain/hooks/cost-journal.sh"
SETTINGS="$CLAUDE_DIR/settings.json"
MARKER="# auto-brain-wrapper"

die() { echo "install.sh: $*" >&2; exit 1; }

command -v python3 >/dev/null || die "python3 is required"
command -v jq >/dev/null || die "jq is required"

# Verified copy into backups/ beside the file. Symlinks are saved as absolute links
# so the backup still resolves.
backup_file() {
  local target="$1" dir name backup
  dir="$(dirname "$target")/backups"
  name="$(basename "$target").$(date +%Y%m%d-%H%M%S-%N).bak"
  backup="$dir/$name"
  mkdir -p "$dir"
  chmod 700 "$dir"
  if [[ -L "$target" ]]; then
    ln -s "$(readlink -f "$target")" "$backup"
    [[ "$(readlink "$backup")" == "$(readlink -f "$target")" ]] || die "backup verification failed for $target"
  else
    cp -a "$target" "$backup"
    cmp -s "$target" "$backup" || die "backup verification failed for $target"
  fi
  echo "backed up $target -> $backup"
}

# 1. Refuse before changing anything if the wrapper slot holds something we cannot account for.
if [[ -e "$WRAPPER" || -L "$WRAPPER" ]] && ! grep -qF "$MARKER" "$WRAPPER" 2>/dev/null && [[ ! -L "$WRAPPER" ]]; then
  die "$WRAPPER exists and is not an auto-brain wrapper. Move it, or set AUTO_BRAIN_BIN_DIR."
fi
if [[ -s "$SETTINGS" ]]; then
  jq empty "$SETTINGS" 2>/dev/null || die "$SETTINGS is not valid JSON. Fix it first."
fi

# 2. Package and hook.
mkdir -p "$BRAIN_HOME/lib"
rm -rf "$BRAIN_HOME/lib/auto_brain"
cp -r "$REPO/src/auto_brain" "$BRAIN_HOME/lib/auto_brain"
find "$BRAIN_HOME/lib/auto_brain" -name __pycache__ -prune -exec rm -rf {} +
chmod +x "$HOOK"

# 3. Global config. Never overwrite a user's edits.
if [[ ! -e "$BRAIN_HOME/config.json" ]]; then
  cp "$REPO/config/global-default.json" "$BRAIN_HOME/config.json"
  echo "wrote $BRAIN_HOME/config.json"
fi

# 4. Wrapper. A symlinked claude is replaced, so remember where it pointed.
mkdir -p "$BIN_DIR"
if [[ -L "$WRAPPER" ]]; then
  readlink -f "$WRAPPER" >"$BRAIN_HOME/real-claude"
  backup_file "$WRAPPER"
  rm "$WRAPPER"
elif [[ -e "$WRAPPER" ]]; then
  rm "$WRAPPER"
fi
cp "$REPO/src/auto_brain/hooks/claude-wrapper.sh" "$WRAPPER"
chmod +x "$WRAPPER"

# 5. Register the UserPromptSubmit hook.
if [[ ! -e "$SETTINGS" ]]; then
  mkdir -p "$CLAUDE_DIR"
  echo '{}' >"$SETTINGS"
fi
if jq -e --arg command "$HOOK" 'any(.hooks.UserPromptSubmit[]?.hooks[]?; .command == $command)' "$SETTINGS" >/dev/null; then
  echo "hook already registered in $SETTINGS"
else
  backup_file "$SETTINGS"
  updated="$(jq --arg command "$HOOK" '
    .hooks //= {} | .hooks.UserPromptSubmit //= []
    | .hooks.UserPromptSubmit += [{"hooks": [{"type": "command", "command": $command, "timeout": 10}]}]
  ' "$SETTINGS")"
  # Redirect into the existing file so its mode and ownership stay as they were.
  printf '%s\n' "$updated" >"$SETTINGS"
fi

# 6. Register the Stop hook (cost journal).
chmod +x "$JOURNAL_HOOK"
if jq -e --arg command "$JOURNAL_HOOK" 'any(.hooks.Stop[]?.hooks[]?; .command == $command)' "$SETTINGS" >/dev/null 2>&1; then
  echo "journal hook already registered in $SETTINGS"
else
  backup_file "$SETTINGS"
  updated="$(jq --arg command "$JOURNAL_HOOK" '
    .hooks //= {} | .hooks.Stop //= []
    | .hooks.Stop += [{"hooks": [{"type": "command", "command": $command, "timeout": 15}]}]
  ' "$SETTINGS")"
  printf '%s\n' "$updated" >"$SETTINGS"
fi

echo "installed. wrapper: $WRAPPER, hook: $HOOK, journal: $JOURNAL_HOOK"
if [[ "$(command -v claude || true)" != "$WRAPPER" ]]; then
  echo "warning: 'claude' on PATH is not $WRAPPER. Put $BIN_DIR before the real claude in PATH." >&2
fi
