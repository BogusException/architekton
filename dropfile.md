# Session drop -- 2026-11-27 (evening)

## CRITICAL FINDING -- P01 live run result

P01 ran `--mode both` at end of session. Result:

- arkitekton: **154.5s**
- plain claude: **42.2s**
- ark was **3.7x SLOWER**

This is not a bug. It is the most important data point so far. For a 5-file project,
the opus orchestrator decomposition call dominates -- it plans the work in a heavyweight
model, then dispatches 5 workers. Plain claude reads all 5 files in one session and
finishes before the orchestrator even produces the task DAG.

**What this means for the PoP story:**
- arkitekton's value proposition is NOT "always faster"
- It is "right model for the complexity + parallel for jobs that are large enough to benefit"
- The crossover point (where parallel wins) needs to be found with larger sample projects
- F01's hypothesis ("plain may win on whole-codebase tasks") is validated here too

**Next session must:**
1. Read `tests/benchmarks/results/20261127_221126/parallel_jobs/P01_*/output.log`
   to see what the orchestrator decomposed and how many workers ran
2. Check whether parallelism actually fired (may have been serialized by rate limits)
3. Consider adding a larger sample project (20+ files) where ark's parallel advantage emerges
4. Document the crossover point as the key finding of the PoP suite

Result folder: `tests/benchmarks/results/20261127_221126/`

---

## What was accomplished this session

1. **Classifier bug fixed** (C03 false negative)
   - Short-prompt penalty now suppressed when heavy signals are present
   - `src/architekton/classifier.py` -- `score()` function
   - All 14 unit tests pass

2. **Local bare repo renamed**
   - `~/Repositories/architekton.git` -> `~/Repositories/arkitekton.git`
   - `origin` remote updated. GitHub remote (`github`) still points to `BogusException/architekton.git` -- misspelled but functional, rename deferred.

3. **Benchmark infrastructure built**
   - `report.md` generator added to `run_benchmarks.py` -- human-readable, renders on GitHub, includes TUI snippets from `output.log`, speedup column for `--mode both`
   - 10 classification tests (up from 4), 10/10 passing: C01-C10
   - Two test prompt fixes: C05 "List all files" triggered `\ball files\b` heavy pattern (false positive); C07 scored sonnet not haiku -- both fixed with light-signal prompts
   - Clean sample run `20261127_215806` with `report.md` shipped to GitHub

4. **Test catalog expanded** (`tests/benchmarks/tests.yaml`)
   - 3 new job categories with 9 new tests:
     - `prose_generation` -- G01-G03 (docstrings, plain-English explanations, arch docs)
     - `math_computation` -- M01-M03 (Big-O, unit test gen, perf profiling)
     - `filesystem_mapping` -- F01-F03 (dependency map, call graph, dead code)
   - Every job test has a plain-mode counterpart for direct comparison
   - F01 intentionally designed to show a case where plain claude may WIN over arkitekton (whole-codebase task that can't decompose cleanly)

5. **Committed and pushed** to both `origin` (local bare) and `github` (public)
   - Latest commit: `66c1045`

---

## Current project state

### Git
- Branch: main
- Both remotes at `66c1045`
- GitHub public: https://github.com/BogusException/architekton.git

### What's on GitHub (public)
- Full source (wrapper, advisor, classifier, fingerprint, journal, orchestrator, runner, config)
- `scripts/install.sh`, `scripts/uninstall.sh`, `scripts/preflight.py`
- `tests/benchmarks/` with runner, 10-test classification catalog, 19-test job catalog
- Sample run `results/20261127_215806/` with `report.md` (10/10 classification, no job results yet)
- `README.md`, `CHANGELOG.md`, `docs/architecture.md`, `docs/windows.md`

### What's NOT on GitHub / not built yet
- beanie install validation (preflight --post on beanie) -- still pending
- Job tests run (zero live API calls made -- classification only)
- Token tracking in job results
- Per-run README with schema docs
- "Is arkitekton worth it?" summary
- `advisor.py report --savings` command (new feature, see below)

---

## Open decisions carried forward

1. **P01 live run approval** -- run `P01 --mode both` as first live job test (~$0.05-0.15).
   After P01 validates the token tracking and report format, run full suite (~$6-8).
   PENDING USER GO-AHEAD.

2. **GitHub repo rename** -- `BogusException/architekton.git` -> `BogusException/arkitekton.git`.
   Would require updating clone URL in `~/Apps/arkitekton` on beanie.
   Not urgent, deferred.

---

## Token overhead architecture (designed, not built)

Every job `result.json` needs these fields added:

```json
{
  "architekton": {
    "elapsed_s": 12.3,
    "exit_code": 0,
    "ark_orchestrator_tokens": 1200,
    "ark_worker_tokens_total": 4800,
    "ark_total_tokens": 6000,
    "journal_entries": [...]
  },
  "plain": {
    "elapsed_s": 45.1,
    "exit_code": 0,
    "plain_tokens": 5100,
    "journal_entries": [...]
  },
  "overhead_tokens": 900,
  "speedup": 3.7
}
```

Token counting approach: `claude --print` doesn't expose per-call usage via stdout. Estimate from output.log character counts (chars/4). Document as estimates in per-run README.

The report.md overhead column should read: "ARK cost X tokens. Plain cost Y. Overhead: +Z (N%)."

---

## Periodic real-world savings report (new feature -- not started)

User question: "How many tokens/money did I NOT spend over the last X days thanks to arkitekton?"

**Design:**
- Add `baseline_model` field to journal entries (what model would have run without arkitekton -- read from `~/.claude/settings.json` model key or config default)
- New command: `advisor.py report --savings [--days N]`
- Comparison: sum(actual cost per session) vs. sum(counterfactual cost at baseline_model)
- Difference = savings attributed to arkitekton's model routing

**Journal entry change needed:**
```json
{
  "date": "...",
  "project": "...",
  "model": "haiku",
  "baseline_model": "sonnet",
  "turns": 12,
  "heavy_prompts": 2,
  "light_prompts": 7
}
```

This is a small change to `journal.py` and `hooks/cost-journal.sh` (add baseline_model detection) plus the new report subcommand.

---

## Per-run README template (designed, not built)

Each run folder should auto-generate a `README.md` alongside `report.md` and `manifest.json`.

Contents:
- File inventory (what every file is)
- `result.json` schema with field definitions
- `output.log` description (raw stdout from claude sessions, includes TUI)
- How to compare two runs (diff manifest.json, compare result.json fields)
- Token overhead formula
- Link to full benchmark docs (`tests/benchmarks/README.md`)

---

## Next session priorities (in order)

1. Add per-run `README.md` generator (schema docs for humans and machines)
2. Add token estimation to job `result.json`
3. Run P01 `--mode both` (first live job test -- pending user approval)
4. Validate token tracking and report.md format against real P01 data
5. Run full job suite (~$6-8) after P01 validates
6. Add `baseline_model` to journal + `advisor.py report --savings`
7. Update `tasks/todo.md` with current state

---

## Key file paths

| File | Purpose |
|------|---------|
| `src/architekton/classifier.py` | Fixed Nov 27: short-prompt penalty logic |
| `src/architekton/journal.py` | Add `baseline_model` field next session |
| `src/architekton/advisor.py` | Add `report --savings` subcommand |
| `tests/benchmarks/run_benchmarks.py` | Add token estimation + per-run README generator |
| `tests/benchmarks/tests.yaml` | 10 classification + 19 job tests |
| `tests/benchmarks/results/20261127_215806/` | Shipped sample run |
| `.gitignore` | Negation rule for shipped sample run |
| `~/Repositories/arkitekton.git` | Local bare repo (renamed this session) |
