#!/usr/bin/env bash
# architekton-wrapper
# Installed as ~/bin/claude. Picks a model at session start, then execs the real claude.
# Any failure falls through to plain claude so the wrapper never blocks a session.

SELF="$(readlink -f "${BASH_SOURCE[0]}")"
BRAIN_HOME="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/architekton"

find_real_claude() {
  local candidate dir recorded
  if [[ -n "${AUTO_BRAIN_REAL_CLAUDE:-}" ]]; then
    echo "$AUTO_BRAIN_REAL_CLAUDE"
    return 0
  fi
  # install.sh records the target when it replaces a symlinked claude.
  if [[ -r "$BRAIN_HOME/real-claude" ]]; then
    recorded="$(<"$BRAIN_HOME/real-claude")"
    if [[ -x "$recorded" ]]; then
      echo "$recorded"
      return 0
    fi
  fi
  local IFS=:
  for dir in $PATH; do
    candidate="$dir/claude"
    [[ -x "$candidate" && ! -d "$candidate" ]] || continue
    [[ "$(readlink -f "$candidate")" == "$SELF" ]] && continue
    echo "$candidate"
    return 0
  done
  return 1
}

REAL="$(find_real_claude)" || {
  echo "architekton: cannot find the real claude binary" >&2
  exit 127
}

[[ "${ARCHITEKTON_DISABLE:-}" == "1" ]] && exec "$REAL" "$@"

# A bare lowercase word is a subcommand (mcp, doctor, ...). Adding --model would break it.
[[ "${1:-}" =~ ^[a-z][a-z0-9-]*$ ]] && exec "$REAL" "$@"

has_explicit_model=0
is_print_mode=0
args=("$@")
for ((i = 0; i < ${#args[@]}; i++)); do
  case "${args[i]}" in
    --model) has_explicit_model=1; explicit_model="${args[i+1]:-}" ;;
    --model=*) has_explicit_model=1; explicit_model="${args[i]#--model=}" ;;
    -p|--print) is_print_mode=1 ;;
  esac
done

if ((has_explicit_model)); then
  # The warn hook needs to know the model even when the user chose it.
  [[ -n "${explicit_model:-}" ]] && export ARCHITEKTON_MODEL="$explicit_model"
  exec "$REAL" "$@"
fi

selection="$(PYTHONPATH="$BRAIN_HOME/lib${PYTHONPATH:+:$PYTHONPATH}" python3 -m architekton.advisor session-start 2>/dev/null)" || selection=""
if [[ -n "$selection" ]]; then
  IFS=$'\t' read -r model source <<<"$selection"
  ((is_print_mode)) || echo "[architekton] Starting with $model ($source)" >&2
  export ARCHITEKTON_MODEL="$model"
  exec "$REAL" --model "$model" "$@"
fi

exec "$REAL" "$@"
