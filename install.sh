#!/usr/bin/env bash
# Installs architekton: package + hook into ~/.claude/architekton, wrapper into ~/bin/claude,
# hook registration in ~/.claude/settings.json. Safe to re-run.
#
# Flags:
#   --yes / -y                skip all prompts, accept defaults
#   ARCHITEKTON_NONINTERACTIVE=1   same effect via environment
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
BRAIN_HOME="$CLAUDE_DIR/architekton"
BIN_DIR="${ARCHITEKTON_BIN_DIR:-$HOME/bin}"
WRAPPER="$BIN_DIR/claude"
HOOK="$BRAIN_HOME/lib/architekton/hooks/architekton-warn.sh"
JOURNAL_HOOK="$BRAIN_HOME/lib/architekton/hooks/cost-journal.sh"
SETTINGS="$CLAUDE_DIR/settings.json"
MARKER="# architekton-wrapper"

# Interactive mode: disabled by env var or --yes/-y flag.
INTERACTIVE=1
[[ "${ARCHITEKTON_NONINTERACTIVE:-0}" == "1" ]] && INTERACTIVE=0
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

# 0. Detect existing install.
if [[ -d "$BRAIN_HOME/lib/architekton" ]]; then
  echo "=== architekton is already installed -- reinstalling ==="
else
  echo "=== Installing architekton ==="
fi
echo ""

# 1. Prerequisites.
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
_is_known_wrapper() { grep -qF "$MARKER" "$1" 2>/dev/null || grep -qF "# auto-brain-wrapper" "$1" 2>/dev/null; }
if [[ -e "$WRAPPER" || -L "$WRAPPER" ]] && ! _is_known_wrapper "$WRAPPER" && [[ ! -L "$WRAPPER" ]]; then
  die "$WRAPPER exists and is not an architekton wrapper. Move it, or set ARCHITEKTON_BIN_DIR."
fi
if [[ -s "$SETTINGS" ]]; then
  jq empty "$SETTINGS" 2>/dev/null || die "$SETTINGS is not valid JSON. Fix it first."
fi

# 2. Package and hook.
mkdir -p "$BRAIN_HOME/lib"
rm -rf "$BRAIN_HOME/lib/architekton"
cp -r "$REPO/src/architekton" "$BRAIN_HOME/lib/architekton"
find "$BRAIN_HOME/lib/architekton" -name __pycache__ -prune -exec rm -rf {} +
chmod +x "$HOOK"

# 3. Global config. Never overwrite a user's edits.
if [[ ! -e "$BRAIN_HOME/config.json" ]]; then
  cp "$REPO/config/.defaults/global.json" "$BRAIN_HOME/config.json"
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
cp "$REPO/src/architekton/hooks/claude-wrapper.sh" "$WRAPPER"
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
SKILL_SRC="$REPO/skills/architekton"
SKILL_DEST="$CLAUDE_DIR/skills/architekton"

if [[ -d "$SKILL_SRC" ]]; then
  echo ""
  echo "=== Optional: /architekton skill ==="
  echo "  The /architekton skill adds a /architekton slash command for the job runner."
  echo "  You can also allow the AI model to suggest it proactively (default: off)."
  echo ""
  _install_skill=$(ask "Install the /architekton skill to $SKILL_DEST?" "Y")
  if [[ "$_install_skill" == "y" ]]; then
    mkdir -p "$SKILL_DEST"
    cp -r "$SKILL_SRC"/. "$SKILL_DEST/"
    chmod +x "$SKILL_DEST/architekton.sh"
    _allow_model=$(ask "Allow the AI model to suggest the job runner proactively?" "N")
    if [[ "$_allow_model" == "y" ]]; then
      sed -i 's/^disable-model-invocation: true/disable-model-invocation: false/' "$SKILL_DEST/SKILL.md"
      echo "  set: model-invocable -- AI can suggest /architekton when appropriate"
    else
      echo "  set: user-only -- invoke with /architekton run \"...\""
    fi
    echo "  installed: $SKILL_DEST"
  else
    echo "  skipped skill install"
  fi
fi

# 8. Mod installation (architekton-warn: in-process warn hook via Claude Code mods API).
MOD_SRC="$REPO/src/mod"
MOD_DEST="$BRAIN_HOME/mods"

mkdir -p "$MOD_DEST/.claude-plugin"
cp -r "$MOD_SRC/architekton-warn" "$MOD_DEST/"
cp "$MOD_SRC/marketplace.json" "$MOD_DEST/.claude-plugin/marketplace.json"

_marketplace_registered=0
if claude plugin marketplace list 2>/dev/null | grep -q "architekton"; then
  _marketplace_registered=1
fi
if [[ "$_marketplace_registered" == "0" ]]; then
  claude plugin marketplace add "$MOD_DEST" 2>/dev/null && _marketplace_registered=1 || true
fi

_mod_installed=0
if claude plugin list 2>/dev/null | grep -q "architekton-warn"; then
  _mod_installed=1
fi
if [[ "$_mod_installed" == "0" && "$_marketplace_registered" == "1" ]]; then
  claude plugin install architekton-warn@architekton 2>/dev/null && _mod_installed=1 || true
fi

if [[ "$_mod_installed" == "1" ]]; then
  echo "mod installed: architekton-warn (restart Claude Code to activate)"
else
  echo "mod: could not auto-install -- run: claude plugin install architekton-warn@architekton"
fi

echo ""
echo "installed. wrapper: $WRAPPER, hook: $HOOK, journal: $JOURNAL_HOOK"
if [[ "$(command -v claude || true)" != "$WRAPPER" ]]; then
  echo "warning: 'claude' on PATH is not $WRAPPER. Put $BIN_DIR before the real claude in PATH." >&2
fi
