# Customizing

## 1. Configuration

Config files are JSON. The global file is `~/.claude/smartmodel/config.json`; project overrides go in `.claude/smartmodel.json` at the project root. Project keys win over global keys. See `config/global-default.json` and `config/project-default.json` for templates.

| Key | Default | Effect |
|-----|---------|--------|
| `enabled` | `true` | Set `false` to disable auto-brain globally without uninstalling |
| `mode` | `"auto"` | `"auto"` selects model at session start; `"advisory"` only warns mid-session |
| `default_model` | `"sonnet"` | Model used when no fingerprint matches and no higher-priority config is set |
| `models.haiku` | `"haiku"` | Alias or full model ID to use for the haiku tier |
| `models.sonnet` | `"sonnet"` | Alias or full model ID to use for the sonnet tier |
| `models.opus` | `"opus"` | Alias or full model ID to use for the opus tier |
| `thresholds.light` | `0.30` | Complexity score at or below this resolves to haiku |
| `thresholds.heavy` | `0.65` | Complexity score at or above this resolves to opus |

**Environment override:** Set `SMARTMODEL_DISABLE=1` to bypass auto-brain for one session without touching config.

## 2. Extension points

- **To add a new fingerprint rule:** edit `src/auto_brain/fingerprint.py`. Add a new block in `detect()` before the `return {"tier": None, ...}` line. Follow the existing pattern: read a file, check a condition, return early with a tier and reason string.
- **To add a new complexity signal:** edit `src/auto_brain/classifier.py`. Add a pattern to `HEAVY_PATTERNS` or `LIGHT_PATTERNS`. Each distinct match adds or subtracts `SIGNAL_WEIGHT` (0.12) from the score.
- **To add a new CLI subcommand:** add a `run_*` function and register it in `build_parser()` in `src/auto_brain/advisor.py`.

## 3. Changing default behaviour

- **Force a specific model for a project:** add `"default_model": "opus"` to `.claude/smartmodel.json` in that project root.
- **Use a pinned model ID instead of an alias:** set `"models": {"opus": "claude-opus-4-7"}` in global config to map the tier to a specific model version.
- **Raise the threshold for Opus:** increase `thresholds.heavy` above `0.65` to require higher complexity before recommending Opus.
- **Switch to advisory-only mode:** set `"mode": "advisory"` to disable automatic model selection at session start while keeping the mid-session warn hook active.
