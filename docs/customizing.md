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
| `pricing.opus.input_per_1m` | `15.00` | $/1M input tokens for opus (used by cost report) |
| `pricing.opus.output_per_1m` | `75.00` | $/1M output tokens for opus |
| `pricing.sonnet.input_per_1m` | `3.00` | $/1M input tokens for sonnet |
| `pricing.sonnet.output_per_1m` | `15.00` | $/1M output tokens for sonnet |
| `pricing.haiku.input_per_1m` | `0.80` | $/1M input tokens for haiku |
| `pricing.haiku.output_per_1m` | `4.00` | $/1M output tokens for haiku |
| `job.orchestrator_model` | `"opus"` | Model used to plan a job (decompose into tasks) |
| `job.worker_model` | `"haiku"` | Default model for each task worker |
| `job.max_parallel` | `4` | Maximum concurrent worker sessions |
| `job.worker_timeout` | `300` | Seconds before a worker is killed |
| `job.worker_max_turns` | `20` | `--max-turns` passed to each worker |
| `job.orchestrator_preamble` | `""` | Text prepended to the orchestrator prompt; set to `/plan\n` to invoke the native `/plan` skill |
| `job.thinking_map` | `{"haiku":"low","sonnet":"med","opus":"high"}` | Maps model tier to the thinking effort label shown in the TUI; modify to change per-tier defaults |
| `job.worker_thinking` | `""` | Force all workers to a fixed effort label (`"low"`, `"med"`, `"high"`, `"ext"`); empty string derives from model via `thinking_map` |

### Thinking effort levels

The `[eff ]` column in the TUI and the `thinking` field in job config use these canonical labels:

| Label | Meaning | Model default |
|-------|---------|---------------|
| `low` | Routine mechanical work | haiku |
| `med` | Moderate analysis | sonnet |
| `high` | Deep reasoning required | opus |
| `ext` | Maximum effort, use sparingly | (none) |

**Aliases** -- the following are accepted in config and in orchestrator JSON output and normalized at runtime with a warning so you can find and fix them:

| Alias | Resolves to |
|-------|-------------|
| `medium`, `normal`, `moderate` | `med` |
| `minimal`, `minimum` | `low` |
| `extreme`, `max`, `maximum`, `extended`, `ultra` | `ext` |

Case is ignored (`HIGH`, `Med`, `high` all work). Unknown values pass through with a warning and are displayed as-is.

**Model values** accept either a tier alias (`haiku`, `sonnet`, `opus`) or a full model ID (`claude-opus-4-7`, `claude-haiku-4-5-20251001`). Unrecognized values emit a warning at session start and will cause workers to fail if the model is unavailable.

**One-off overrides without editing config** -- the `run` subcommand accepts CLI flags that take precedence over config for a single job:

```bash
# Use a different orchestrator for one job
PYTHONPATH=src python -m auto_brain.advisor run --orchestrator-model sonnet "my goal"

# Override worker model, parallelism, and timeout
PYTHONPATH=src python -m auto_brain.advisor run \
  --worker-model sonnet \
  --max-parallel 2 \
  --timeout 600 \
  "build a REST API"

# Force all workers to high thinking effort
PYTHONPATH=src python -m auto_brain.advisor run --thinking high "audit the codebase"
```

Run `python -m auto_brain.advisor run --help` for the full flag reference.

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
