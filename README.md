# auto-brain

Model advisor for Claude Code. Automatically selects the right Claude model (Opus / Sonnet / Haiku) at session start based on project type and prompt complexity. Warns mid-session when the active model is mismatched for the task.

## Install

```bash
bash install.sh
```

Requires Python 3.9+, Claude Code, and `jq`. See `docs/install.md` for full prerequisites and verification steps.

## How it works

The installer places a wrapper at `~/bin/claude` that intercepts every session start. It calls `advisor.py session-start`, which checks project files and config to pick a model, then launches the real Claude with `--model <tier>`. A `UserPromptSubmit` hook then scores each prompt as it arrives and injects a one-line nudge when the active model is a mismatch.

No network calls. No LLM calls. Classification runs in under 50ms.

## Advisor CLI

```bash
# Score a prompt
echo "refactor the auth module" | python -m auto_brain.advisor classify

# Show what model the wrapper would select (and why)
python -m auto_brain.advisor session-start

# Show current config and session state
python -m auto_brain.advisor status

# Disable globally
python -m auto_brain.advisor toggle off

# Re-enable
python -m auto_brain.advisor toggle on
```

## Configuration

Global config: `~/.claude/smartmodel/config.json`. Project overrides: `.claude/smartmodel.json`.

| Key | Default | Effect |
|-----|---------|--------|
| `enabled` | `true` | Set `false` to disable without uninstalling |
| `mode` | `"auto"` | `"auto"` selects model at start; `"advisory"` only warns mid-session |
| `default_model` | `"sonnet"` | Fallback when no fingerprint matches |
| `thresholds.light` | `0.30` | Complexity at or below this -> Haiku |
| `thresholds.heavy` | `0.65` | Complexity at or above this -> Opus |

Set `SMARTMODEL_DISABLE=1` to bypass for a single session without changing config.

See `docs/customizing.md` for the full config reference and extension points.

## Tests

```bash
bash test.sh
```
