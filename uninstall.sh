#!/usr/bin/env bash
# Removes architekton from the system. Safe to re-run.
# Leaves config.json and cost-journal.jsonl (user data) intact.
#
# Flags:
#   --yes / -y                      skip all prompts, accept defaults
#   --purge                         also remove config.json and cost-journal.jsonl
#   ARCHITEKTON_NONINTERACTIVE=1     same as --yes via environment
set -euo pipefail

CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
BRAIN_HOME="$CLAUDE_DIR/architekton"
BIN_DIR="${ARCHITEKTON_BIN_DIR:-$HOME/bin}"
WRAPPER="$BIN_DIR/claude"
SETTINGS="$CLAUDE_DIR/settings.json"
MARKER="# architekton-wrapper"
REAL_CLAUDE_FILE="$BRAIN_HOME/real-claude"
SKILL_DEST="$CLAUDE_DIR/skills/architekton"

INTERACTIVE=1
PURGE=0
[[ "${ARCHITEKTON_NONINTERACTIVE:-0}" == "1" ]] && INTERACTIVE=0
for _arg in "$@"; do
  [[ "$_arg" == "--yes" || "$_arg" == "-y" ]] && INTERACTIVE=0
  [[ "$_arg" == "--purge" ]] && PURGE=1
done

die() { echo "uninstall.sh: $*" >&2; exit 1; }

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

echo "=== architekton uninstall ==="
echo ""

# Early exit if nothing to uninstall.
_wrapper_is_ours=0
{ grep -qF "$MARKER" "$WRAPPER" 2>/dev/null || grep -qF "# auto-brain-wrapper" "$WRAPPER" 2>/dev/null; } && _wrapper_is_ours=1
_has_pkg=0
[[ -d "$BRAIN_HOME/lib/architekton" ]] && _has_pkg=1
if [[ "$_wrapper_is_ours" == "0" && "$_has_pkg" == "0" ]]; then
  echo "architekton does not appear to be installed. Nothing to remove."
  exit 0
fi

# 1. Remove wrapper.
if [[ -e "$WRAPPER" || -L "$WRAPPER" ]]; then
  if grep -qF "$MARKER" "$WRAPPER" 2>/dev/null || grep -qF "# auto-brain-wrapper" "$WRAPPER" 2>/dev/null; then
    _remove=$(ask "Remove wrapper $WRAPPER?" "Y")
    if [[ "$_remove" == "y" ]]; then
      # Restore a saved real-claude symlink if one was recorded.
      if [[ -s "$REAL_CLAUDE_FILE" ]]; then
        _real="$(cat "$REAL_CLAUDE_FILE")"
        if [[ -x "$_real" ]]; then
          ln -sf "$_real" "$WRAPPER"
          echo "restored $WRAPPER -> $_real"
        else
          rm "$WRAPPER"
          echo "removed $WRAPPER (real-claude path '$_real' not found -- left PATH as-is)"
        fi
      else
        rm "$WRAPPER"
        echo "removed $WRAPPER"
      fi
    else
      echo "skipped wrapper removal"
    fi
  else
    echo "SKIP: $WRAPPER exists but is not an architekton wrapper"
  fi
else
  echo "wrapper not present, skipping"
fi

# 2. Remove hooks from settings.json.
if [[ -s "$SETTINGS" ]] && jq empty "$SETTINGS" 2>/dev/null; then
  _has_hooks=$(jq '
    (.hooks.UserPromptSubmit // [] | map(.hooks // [] | map(.command) | flatten) | flatten | map(select(test("architekton"))) | length) +
    (.hooks.Stop // [] | map(.hooks // [] | map(.command) | flatten) | flatten | map(select(test("architekton"))) | length)
  ' "$SETTINGS")
  if [[ "$_has_hooks" -gt 0 ]]; then
    _rm_hooks=$(ask "Remove architekton hooks from $SETTINGS?" "Y")
    if [[ "$_rm_hooks" == "y" ]]; then
      _updated="$(jq '
        .hooks.UserPromptSubmit |= (if . then map(select(.hooks | map(.command | test("architekton")) | any | not)) else . end) |
        .hooks.Stop             |= (if . then map(select(.hooks | map(.command | test("architekton")) | any | not)) else . end)
      ' "$SETTINGS")"
      printf '%s\n' "$_updated" >"$SETTINGS"
      echo "removed architekton hooks from $SETTINGS"
    else
      echo "skipped hook removal"
    fi
  else
    echo "no architekton hooks found in $SETTINGS"
  fi
fi

# 3. Remove installed package.
if [[ -d "$BRAIN_HOME/lib/architekton" ]]; then
  _rm_pkg=$(ask "Remove installed package $BRAIN_HOME/lib/architekton?" "Y")
  if [[ "$_rm_pkg" == "y" ]]; then
    rm -rf "$BRAIN_HOME/lib/architekton"
    echo "removed $BRAIN_HOME/lib/architekton"
    # Remove lib dir if now empty.
    rmdir "$BRAIN_HOME/lib" 2>/dev/null && echo "removed $BRAIN_HOME/lib" || true
  else
    echo "skipped package removal"
  fi
else
  echo "package not installed, skipping"
fi

# 4. Remove skill (optional).
if [[ -d "$SKILL_DEST" ]]; then
  _rm_skill=$(ask "Remove skill $SKILL_DEST?" "Y")
  if [[ "$_rm_skill" == "y" ]]; then
    rm -rf "$SKILL_DEST"
    echo "removed $SKILL_DEST"
  else
    echo "skipped skill removal"
  fi
else
  echo "skill not installed, skipping"
fi

# 5. Clean up real-claude record.
[[ -f "$REAL_CLAUDE_FILE" ]] && rm "$REAL_CLAUDE_FILE" && echo "removed $REAL_CLAUDE_FILE"

# 6. Optional purge of user data.
if [[ "$PURGE" == "1" ]]; then
  echo ""
  echo "=== Purge mode: removing user data ==="
  _config="$BRAIN_HOME/config.json"
  _journal="$BRAIN_HOME/cost-journal.jsonl"
  [[ -f "$_config"  ]] && rm "$_config"  && echo "purged $_config"
  [[ -f "$_journal" ]] && rm "$_journal" && echo "purged $_journal"
  # Remove architekton dir if now empty.
  rmdir "$BRAIN_HOME" 2>/dev/null && echo "removed $BRAIN_HOME" || true
else
  echo ""
  echo "Config and journal preserved at $BRAIN_HOME"
  echo "Re-run with --purge to remove them."
fi

echo ""
echo "Done."
