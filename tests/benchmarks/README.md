# architekton benchmark suite

This benchmark suite measures architekton's real-world performance: cost savings, wall-clock time, and output quality compared to running the same jobs without it. The results are designed to be published -- concrete numbers that let users decide whether architekton is worth using for their workloads.

---

## What it tests

There are five test categories. All categories share a single test catalog (`tests.yaml`). The `--mode` switch at run time controls whether architekton handles each test or plain claude does -- the test prompts never change.

| Category | What it measures |
|---|---|
| `classification` | Whether architekton selects the right model family for a prompt. Fast and free -- no session is started. |
| `single_session` | A single Claude session. architekton mode uses the wrapper for automatic model selection; plain mode calls claude directly. |
| `parallel_jobs` | The main feature. architekton decomposes a job into parallel tasks; plain mode runs the same job in one serial session. Wall-clock and cost differences are stark here. |
| `thinking_levels` | The same parallel job run four times with thinking=low, med, high, ext. Helps you decide whether paying for more thinking actually improves output. |
| `cost_comparison` | Head-to-head: architekton auto config vs plain claude on the same task. Designed to be run with `--mode both` so both sides appear in one report. |

---

## Quick start

Install PyYAML if you haven't already (the runner needs it to read `tests.yaml`):

```bash
pip install pyyaml
```

Or, if you are using the dev environment:

```bash
bash dev-install.sh      # creates .venv and installs dev dependencies
source .venv/bin/activate
```

### Run everything with architekton

```bash
python tests/benchmarks/run_benchmarks.py --mode architekton
```

### Run everything without architekton (baseline)

```bash
python tests/benchmarks/run_benchmarks.py --mode plain
```

### Run both and get a side-by-side comparison

```bash
python tests/benchmarks/run_benchmarks.py --mode both
```

### See what would run without spending anything

```bash
python tests/benchmarks/run_benchmarks.py --dry-run
```

---

## Common filters

```bash
# Run only classification tests (free, no API calls)
python tests/benchmarks/run_benchmarks.py --category classification

# Run the parallel job category with architekton
python tests/benchmarks/run_benchmarks.py --category parallel_jobs --mode architekton

# Run a specific test
python tests/benchmarks/run_benchmarks.py --test P01

# Run multiple specific tests
python tests/benchmarks/run_benchmarks.py --test T01 T02 T03 T04

# Run the thinking-level comparison (architekton mode, all four levels)
python tests/benchmarks/run_benchmarks.py --category thinking_levels --mode architekton

# Run cost comparison tests both ways
python tests/benchmarks/run_benchmarks.py --category cost_comparison --mode both
```

---

## Understanding `--mode`

This is the most important option. It controls how the runner executes each test. The test prompts are identical regardless of mode -- only the execution path changes.

**`--mode architekton`** (default when the wrapper is installed)

The runner calls `python -m architekton.advisor run` for job tests. architekton:
- Sends the job to an Opus orchestrator that breaks it into tasks
- Dispatches tasks to parallel haiku workers (or whichever model the flags specify)
- Collects results and displays a live status board

**`--mode plain`**

The runner calls the real `claude` binary directly with `--print -p "<job>"`. This is a single session with no model routing and no parallelism. It represents what you would do without architekton: paste the job description into one claude session and wait.

**`--mode both`**

Runs each test twice -- architekton first, then plain -- and writes both results. The comparison report shows time and journal entries for each. Use this for the `cost_comparison` category.

---

## Comparing with vs without architekton: what to look for

When you run `--mode both`, each test shows:

- **Wall-clock time**: architekton's parallel workers typically finish 2-5x faster on tasks that decompose well (like "summarize each file").
- **Cost journal entries**: architekton uses multiple short haiku sessions; plain claude uses one longer session on whatever model is globally configured. If you are configured for opus globally, the difference can be 10-20x in cost.
- **Output quality**: subjective -- read the result files in `results/<run_id>/`. The `P-` series writes one file per source file, so comparisons are easy.

The classification tests have no "plain" equivalent (there is no classifier without architekton). The runner marks them as skipped in plain mode and notes why.

---

## Thinking levels

The `T01`-`T04` tests run the same parallel job with thinking=low, med, high, ext. Here is what each level means:

| Level | What it does | Default for |
|---|---|---|
| `low` | Minimal extended thinking | haiku workers |
| `med` | Moderate reasoning budget | sonnet workers |
| `high` | Deep reasoning | opus workers (and orchestrator) |
| `ext` | Maximum effort | (use sparingly) |

The architekton default is to match thinking level to model tier (`thinking_map` in config). The question the T-series answers: does bumping haiku workers to `high` thinking produce opus-quality output at haiku prices, or does it just cost more with diminishing returns?

Run all four and read the result files side-by-side. The numbers will show the cost; your eyes will show the quality.

---

## Output files

Each run creates a timestamped directory under `tests/benchmarks/results/`, and each test gets its own datetime-stamped folder under its category:

```
results/
  20261126_005143/                      one run
    manifest.json                      overall run summary (mode, timestamps, test statuses, test dirs)
    classification/
      C01_20261126_005143/
        result.json                    status, timing, expected vs selected model
    parallel_jobs/
      P01_20261126_005210/
        result.json                    status, timing, exit codes, journal entries
        output.log                     raw stdout+stderr from the test session(s)
    ...
```

`results/` is gitignored -- your run data stays local. Share `manifest.json` and the `result.json` files with teammates when you want to compare runs across machines. Runs from before this layout (flat `<test_id>.json` files) can still be summarized.

### Summarizing a previous run

```bash
python tests/benchmarks/run_benchmarks.py --summarize results/20261124_120000/
```

### Comparing two runs

```bash
python tests/benchmarks/run_benchmarks.py --summarize results/20261124_120000/ results/20261124_140000/
```

---

## Adding or modifying tests

All test definitions live in `tests.yaml`. That is the only file you edit.

To add a test:
1. Open `tests.yaml`
2. Find the category section you want (or add a new one under `categories:`)
3. Append a new entry to `tests:` with a unique `id`

To change a prompt: edit the `job:` or `prompt:` field in `tests.yaml`. The change applies to both architekton and plain modes automatically.

To remove a test: delete its entry from `tests.yaml`.

---

## The sample project

Tests in the `parallel_jobs`, `thinking_levels`, and `cost_comparison` categories operate on `sample_jobs/small_project/`, a small self-contained Python project included with the benchmark suite. It has five modules:

| File | What it does |
|---|---|
| `data_loader.py` | Reads CSV and JSON files, validates required columns |
| `transformer.py` | Applies named transformation functions to records |
| `validator.py` | Runs named validation rules and produces a report |
| `reporter.py` | Formats a ValidationReport as text or JSON |
| `cli.py` | Command-line entry point wiring all four modules together |

This is a deliberately realistic Python project -- small enough to run cheaply, complex enough to produce meaningful reviews and summaries.

---

## Cost estimates

Each test shows a `cost_note` in `tests.yaml` and in the dry-run output. These are rough estimates based on typical token counts. Actual cost depends on:

- Your globally configured model (affects plain mode)
- Whether the orchestrator produces many tasks or few
- How verbose each worker's output is

Run `--dry-run` first to review the test list and estimates. Use `--category classification` to validate the classifier for free before spending on job tests.

---

## Requirements

- Python 3.9+
- PyYAML (`pip install pyyaml`)
- architekton installed (`bash scripts/install.sh`) for `--mode architekton`
- Claude Code installed and authenticated for any mode that calls claude
- `~/bin/claude` on your PATH before the system claude (architekton mode)
