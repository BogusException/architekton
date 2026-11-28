# architekton benchmark run — 20261127_225643

## Files in this directory

- `manifest.json` — machine-readable run summary: all test IDs, statuses, timestamps, and paths
- `report.md` — human-readable report with tables and session output snippets; renders on GitHub
- `<category>/<test_id>_<timestamp>/result.json` — per-test result with timing, exit codes, journal entries, and token estimates
- `<category>/<test_id>_<timestamp>/output.log` — raw stdout/stderr from the claude session(s); includes the architekton TUI status lines for job tests

## result.json schema

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Test identifier (e.g. `P01`) |
| `name` | string | Human-readable test name |
| `category` | string | Category group (e.g. `parallel_jobs`) |
| `status` | string | `pass`, `fail`, `skipped`, `error`, `interrupted`, or `dry-run` |
| `cost_note` | string | Rough cost estimate from tests.yaml |
| `token_note` | string | How token counts were estimated |
| `architekton.exit_code` | int | Process exit code for the architekton run |
| `architekton.elapsed_s` | float | Wall-clock seconds for the architekton run |
| `architekton.ark_total_tokens` | int | Estimated total tokens across all architekton sessions |
| `architekton.journal_entries` | array | Cost journal entries written during the architekton run |
| `plain.exit_code` | int | Process exit code for the plain-claude run |
| `plain.elapsed_s` | float | Wall-clock seconds for the plain-claude run |
| `plain.plain_tokens` | int | Estimated total tokens for the plain-claude run |
| `plain.journal_entries` | array | Cost journal entries written during the plain run |
| `overhead_tokens` | int | Estimated extra tokens architekton used vs plain (0 if ark was cheaper) |
| `speedup` | float | `plain_elapsed / ark_elapsed` — values > 1 mean ark was faster |

## output.log format

Each log file has one or two sections separated by `====` lines:

```
==== [architekton] <command> ====
... architekton TUI output and job logs ...
[architekton] exit=0 elapsed=154.5s

==== [plain] <command> ====
... plain claude output ...
[plain] exit=0 elapsed=42.2s
```

## Comparing two runs

```bash
# Compare manifest summaries
diff results/RUN_A/manifest.json results/RUN_B/manifest.json

# Check timing for a specific test
jq '.architekton.elapsed_s, .plain.elapsed_s' results/RUN_A/parallel_jobs/P01_*/result.json
```

## Token overhead formula

```
overhead_tokens = max(0, ark_total_tokens - plain_tokens)
overhead_pct    = overhead_tokens / plain_tokens * 100  (if plain_tokens > 0)
```

Token counts are estimated from journal turn counts using 500 input + 1500 output tokens per turn.
Actual token usage may differ by \u00b150% depending on prompt and context length.

## Full benchmark documentation

See `tests/benchmarks/README.md` for the test catalog, category descriptions, and instructions
for adding new tests.
