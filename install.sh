#!/usr/bin/env bash
# Installs auto-brain: package + hook into ~/.claude/smartmodel, wrapper into ~/bin/claude,
# hook registration in ~/.claude/settings.json. Safe to re-run.
#
# Flags:
#   --yes / -y                skip all prompts, accept defaults
#   AUTO_BRAIN_NONINTERACTIVE=1   same effect via environment
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

# Interactive mode: disabled by env var or --yes/-y flag.
INTERACTIVE=1
[[ "${AUTO_BRAIN_NONINTERACTIVE:-0}" == "1" ]] && INTERACTIVE=0
for _arg in "$@"; do
  [[ "$_arg" == "--yes" || "$_arg" == "-y" ]] && INTERACTIVE=0
done

die() { echo "install.sh: $*" >&2; exit 1; }

# ask PROMPT DEFAULT -- prints "y" or "n". DEFAULT must be Y or N (uppercase).
ask() {
  local prompt="$1" default="${2:-Y}" yn
  if [[ "$INTERACTIVE" == "0" ]]; then
    printf '%s\n' "${default,,}"
    return
  fi
  printf '%s [%s]: ' "$prompt" "$default" >/dev/tty
  read -r yn </dev/tty 2>/dev/null || { printf '%s\n' "${default,,}"; return; }
  yn="${yn:-$default}"
  printf '%s\n' "${yn:0:1}" | tr '[:upper:]' '[:lower:]'
}

# 0. Prerequisites.
echo "=== Checking prerequisites ==="
_prereq_ok=1

if command -v python3 >/dev/null 2>&1; then
  echo "  OK:      $(python3 --version 2>&1)"
else
  echo "  MISSING: python3  (required -- install Python 3.9+)"
  _prereq_ok=0
fi

if command -v jq >/dev/null 2>&1; then
  echo "  OK:      jq $(jq --version 2>&1)"
else
  echo "  MISSING: jq  (required -- install via package manager)"
  _prereq_ok=0
fi

_path_ok=0
IFS=':' read -ra _path_parts <<< "$PATH"
for _p in "${_path_parts[@]}"; do
  # Expand leading ~ so we match both ~/bin and /home/user/bin forms.
  _p_expanded="${_p/#\~/$HOME}"
  [[ "$_p_expanded" == "$BIN_DIR" ]] && _path_ok=1 && break
done
if [[ "$_path_ok" == "1" ]]; then
  echo "  OK:      $BIN_DIR is in PATH"
else
  echo "  WARNING: $BIN_DIR is not in PATH"
  echo "           Add to your shell profile:  export PATH=\"$BIN_DIR:\$PATH\""
fi

[[ "$_prereq_ok" == "1" ]] || die "Missing prerequisites above. Install them and re-run."
echo ""

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

# 7. Skill installation (optional).
SKILL_SRC="$REPO/skills/auto-brain"
SKILL_DEST="$CLAUDE_DIR/skills/auto-brain"

if [[ -d "$SKILL_SRC" ]]; then
  echo ""
  echo "=== Optional: /auto-brain skill ==="
  echo "  The /auto-brain skill adds a /auto-brain slash command for the job runner."
  echo "  You can also allow the AI model to suggest it proactively (default: off)."
  echo ""
  _install_skill=$(ask "Install the /auto-brain skill to $SKILL_DEST?" "Y")
  if [[ "$_install_skill" == "y" ]]; then
    mkdir -p "$SKILL_DEST"
    cp -r "$SKILL_SRC"/. "$SKILL_DEST/"
    chmod +x "$SKILL_DEST/auto-brain.sh"
    _allow_model=$(ask "Allow the AI model to suggest the job runner proactively?" "N")
    if [[ "$_allow_model" == "y" ]]; then
      sed -i 's/^disable-model-invocation: true/disable-model-invocation: false/' "$SKILL_DEST/SKILL.md"
      echo "  set: model-invocable -- AI can suggest /auto-brain when appropriate"
    else
      echo "  set: user-only -- invoke with /auto-brain run \"...\""
    fi
    echo "  installed: $SKILL_DEST"
  else
    echo "  skipped skill install"
  fi
fi

echo ""
echo "installed. wrapper: $WRAPPER, hook: $HOOK, journal: $JOURNAL_HOOK"
if [[ "$(command -v claude || true)" != "$WRAPPER" ]]; then
  echo "warning: 'claude' on PATH is not $WRAPPER. Put $BIN_DIR before the real claude in PATH." >&2
fi
