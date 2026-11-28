#!/usr/bin/env python3
"""
architekton benchmark runner

Runs tests from tests.yaml and writes per-test JSON logs to results/.

Usage
-----
  # Run all tests (prompt to confirm costly ones)
  python run_benchmarks.py

  # Run with architekton (default when wrapper is on PATH)
  python run_benchmarks.py --mode architekton

  # Run WITHOUT architekton (plain claude, no model routing)
  python run_benchmarks.py --mode plain

  # Run each test TWICE and produce a side-by-side comparison
  python run_benchmarks.py --mode both

  # Run only the architekton side, loading cached plain results for comparison
  python run_benchmarks.py --mode ark-only

  # Save plain results to .baseline/ for future ark-only runs
  python run_benchmarks.py --mode plain --save-baseline

  # Seed .baseline/ from an existing run (no API calls)
  python run_benchmarks.py --mode plain --save-baseline --baseline-from 20261127_225643

  # Filter by category or test ID
  python run_benchmarks.py --category parallel_jobs
  python run_benchmarks.py --test P01
  python run_benchmarks.py --category thinking_levels --test T01 T02 T03

  # Dry run: show what would run without spending anything
  python run_benchmarks.py --dry-run

  # Summarize a previous run (or combine multiple runs)
  python run_benchmarks.py --summarize results/run_20261124_120000/

Modes explained
---------------
  architekton  Uses 'python -m architekton.advisor run' for job tests and
               the architekton classifier for classification tests. This is
               the normal mode for measuring what architekton does.

  plain        Uses the real claude binary directly (bypasses the wrapper).
               Same prompts, no model routing, no parallelism -- just one
               claude session per test. Measures the baseline without architekton.

  both         Runs each test twice (architekton first, plain second) and
               writes a comparison report. Use this for the cost_comparison
               category or any head-to-head you want to publish.

  ark-only     Runs only the architekton side. Loads the matching plain result
               from results/.baseline/<test_id>.json (cached from a prior plain
               run) so you get a comparison without paying for plain again.
               Use --baseline-from <run_id> to point at a specific run instead.

Output
------
Each run writes to results/<run_id>/ (run_id = YYYYMMDD_HHMMSS):
  manifest.json                              summary of the whole run
  <category>/<test_id>_<YYYYMMDD_HHMMSS>/    one folder per test, stamped when it ran
    result.json                              timing, exit code, journal entries, notes
    output.log                               raw stdout + stderr (job tests only)
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    # stdlib fallback: minimal YAML subset parser (handles our tests.yaml structure)
    yaml = None


# ── Paths ──────────────────────────────────────────────────────────────────────

REPO_ROOT   = Path(__file__).resolve().parent.parent.parent
BENCH_DIR   = Path(__file__).resolve().parent
TESTS_FILE  = BENCH_DIR / "tests.yaml"
RESULTS_DIR         = BENCH_DIR / "results"
BASELINE_DIR        = RESULTS_DIR / ".baseline"
TIMING_HISTORY_FILE = RESULTS_DIR / ".timing_history.json"

CLAUDE_DIR  = Path(os.environ.get("CLAUDE_CONFIG_DIR", "") or Path.home() / ".claude")
BRAIN_HOME  = CLAUDE_DIR / "architekton"
REAL_CLAUDE_FILE = BRAIN_HOME / "real-claude"
JOURNAL_FILE     = BRAIN_HOME / "cost-journal.jsonl"


# ── YAML loading ───────────────────────────────────────────────────────────────

def _load_yaml(path: Path) -> dict:
    """Load YAML, using PyYAML if available, else a stdlib json fallback.

    If PyYAML is not installed, we cannot parse the YAML file and must
    tell the user how to install it.
    """
    if yaml is not None:
        with open(path) as fh:
            return yaml.safe_load(fh)
    # PyYAML not available. Try the stdlib json parser on a .json twin.
    json_path = path.with_suffix(".json")
    if json_path.exists():
        with open(json_path) as fh:
            return json.load(fh)
    sys.exit(
        "PyYAML is not installed and no tests.json fallback exists.\n"
        "Install PyYAML:  pip install pyyaml\n"
        "Or activate the project venv first:  source .venv/bin/activate"
    )


# ── Real claude path ───────────────────────────────────────────────────────────

def _find_real_claude() -> str:
    """Return the path to the real (non-wrapper) claude binary."""
    if REAL_CLAUDE_FILE.exists():
        path = REAL_CLAUDE_FILE.read_text().strip()
        if path and Path(path).is_file():
            return path
    # Fall back to searching PATH for claude, excluding the architekton wrapper.
    for entry in os.environ.get("PATH", "").split(":"):
        candidate = Path(entry) / "claude"
        if candidate.is_file():
            # Skip if it is the architekton wrapper.
            try:
                content = candidate.read_text(errors="ignore")
                if "architekton-wrapper" in content or "auto-brain-wrapper" in content:
                    continue
            except OSError:
                pass
            return str(candidate)
    sys.exit(
        "Cannot find the real claude binary.\n"
        "architekton records it at ~/.claude/architekton/real-claude after install.\n"
        "If you have not run scripts/install.sh, run it first.\n"
        "Or set REAL_CLAUDE=/path/to/claude in your environment."
    )


# ── Cost journal helpers ───────────────────────────────────────────────────────

def _journal_entry_count() -> int:
    """Return the current number of lines in the cost journal."""
    if not JOURNAL_FILE.exists():
        return 0
    with open(JOURNAL_FILE) as fh:
        return sum(1 for _ in fh)


def _journal_new_entries(before: int) -> list[dict]:
    """Return journal entries added since 'before' was recorded."""
    if not JOURNAL_FILE.exists():
        return []
    entries = []
    with open(JOURNAL_FILE) as fh:
        for i, line in enumerate(fh):
            if i < before:
                continue
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries


# ── Timing history ─────────────────────────────────────────────────────────────

def _load_timing_history() -> dict:
    if not TIMING_HISTORY_FILE.exists():
        return {}
    try:
        return json.loads(TIMING_HISTORY_FILE.read_text())
    except Exception:
        return {}


def _record_timing(test_id: str, mode: str, elapsed_s: float) -> None:
    history = _load_timing_history()
    key = f"{test_id}_{mode}"
    entries = history.get(key, [])
    entries.append({"elapsed_s": round(elapsed_s, 1), "ts": datetime.now().isoformat()})
    history[key] = entries[-10:]
    TIMING_HISTORY_FILE.write_text(json.dumps(history, indent=2))


def _eta_info(test_id: str, mode: str, history: dict) -> str:
    """Return a one-line timing hint for a test based on history."""
    key = f"{test_id}_{mode}"
    entries = history.get(key, [])
    if not entries:
        return ""
    avg = sum(e["elapsed_s"] for e in entries) / len(entries)
    last = entries[-1]["elapsed_s"]
    n = len(entries)
    avg_fmt = f"{avg / 60:.1f}m" if avg >= 60 else f"{avg:.0f}s"
    return f"avg {avg_fmt} ({n} run{'s' if n > 1 else ''}, last {last:.0f}s)"


# ── Baseline cache ──────────────────────────────────────────────────────────────

def _save_baseline(test_id: str, plain_data: dict) -> None:
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    (BASELINE_DIR / f"{test_id}.json").write_text(json.dumps(plain_data, indent=2))


def _load_baseline(test_id: str) -> dict | None:
    path = BASELINE_DIR / f"{test_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _find_result_in_run(run_dir: Path, test_id: str) -> dict | None:
    """Find the result.json for test_id in a previous run directory."""
    for result_file in run_dir.glob(f"*/{test_id}_*/result.json"):
        try:
            return json.loads(result_file.read_text())
        except Exception:
            pass
    return None


# ── Test runner ────────────────────────────────────────────────────────────────

def _run_classify(test: dict, mode: str, run_dir: Path, dry_run: bool) -> dict:
    """Execute a classification test and return a result dict."""
    prompt = test["prompt"]
    expected = test.get("expected", "")

    if dry_run:
        print(f"  [dry-run] classify: {prompt[:60]}...")
        return {"status": "dry-run", "expected": expected}

    advisor = [
        sys.executable, "-m", "architekton.advisor", "classify", prompt,
    ]

    # For 'plain' mode: classification has no meaning (there is no classifier
    # without architekton). We skip the test and note it in the result.
    if mode == "plain":
        return {
            "status": "skipped",
            "reason": "Classification tests only apply to architekton mode.",
        }

    start = time.monotonic()
    result = subprocess.run(
        advisor, capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    elapsed = time.monotonic() - start

    try:
        selected = json.loads(result.stdout).get("recommended_model", "")
    except json.JSONDecodeError:
        selected = ""
    passed = selected == expected if expected else True

    return {
        "status": "pass" if passed else "fail",
        "elapsed_s": round(elapsed, 2),
        "selected_model": selected,
        "expected": expected,
        "stdout": result.stdout[:2000],
        "stderr": result.stderr[:1000],
    }


def _build_architekton_cmd(test: dict) -> list[str]:
    extra_flags = test.get("architekton_flags") or []
    job = test["job"].replace("\n", " ").strip()
    return [
        sys.executable, "-m", "architekton.advisor", "run",
        *extra_flags,
        job,
    ]


def _build_plain_cmd(test: dict, real_claude: str) -> list[str]:
    extra_flags = test.get("plain_flags") or []
    job = test["job"].replace("\n", " ").strip()
    return [
        real_claude, "--print", "-p",
        *extra_flags,
        job,
    ]


def _run_job(test: dict, mode: str, test_dir: Path, dry_run: bool, real_claude: str,
             test_id: str = "", save_baseline: bool = False,
             baseline_from: Path | None = None) -> dict:
    """Execute a job test in the requested mode and return a result dict."""
    workdir = str(REPO_ROOT / test.get("workdir", "."))
    log_file = test_dir / "output.log"

    # Baseline seeding: --mode plain --save-baseline --baseline-from <run_dir>
    # Copies plain results from an existing run rather than re-running.
    if mode == "plain" and save_baseline and baseline_from is not None:
        if dry_run:
            candidates = list(baseline_from.glob(f"*/{test_id}_*/result.json"))
            found = "found" if candidates else "not found in source"
            print(f"  [dry-run] seed baseline {test_id}: {found}")
            return {"status": "dry-run"}
        existing = _find_result_in_run(baseline_from, test_id)
        if existing and "plain" in existing:
            _save_baseline(test_id, existing["plain"])
            return {"status": "seeded", "plain": existing["plain"]}
        return {
            "status": "skipped",
            "reason": f"no plain sub-dict for {test_id} in {baseline_from.name}",
        }

    # Build command list for execution.
    cmds = []
    if mode in ("architekton", "both", "ark-only"):
        cmds.append(("architekton", _build_architekton_cmd(test)))
    if mode in ("plain", "both"):
        cmds.append(("plain", _build_plain_cmd(test, real_claude)))

    if dry_run:
        for label, cmd in cmds:
            print(f"  [dry-run] [{label}] {' '.join(cmd[:6])} ...")
        return {"status": "dry-run"}

    results = {}
    with open(log_file, "w") as log:
        for label, cmd in cmds:
            log.write(f"\n{'='*60}\n[{label}] {' '.join(cmd)}\n{'='*60}\n")
            before = _journal_entry_count()
            start = time.monotonic()
            proc = subprocess.run(
                cmd,
                stdout=log,
                stderr=log,
                cwd=workdir,
                text=True,
            )
            elapsed = time.monotonic() - start
            new_entries = _journal_new_entries(before)
            results[label] = {
                "exit_code": proc.returncode,
                "elapsed_s": round(elapsed, 2),
                "journal_entries": new_entries,
            }
            log.write(f"\n[{label}] exit={proc.returncode} elapsed={elapsed:.1f}s\n")

    # For ark-only mode: attach cached plain baseline for comparison.
    if mode == "ark-only":
        cached: dict | None = None
        if baseline_from is not None:
            existing = _find_result_in_run(baseline_from, test_id)
            if existing and "plain" in existing:
                cached = existing["plain"]
        if cached is None:
            cached = _load_baseline(test_id)
        if cached is not None:
            results["plain"] = cached
        else:
            results["plain_note"] = "no cached baseline; run --mode plain --save-baseline first"

    # Save plain result to baseline cache when requested.
    if save_baseline and "plain" in results and baseline_from is None:
        _save_baseline(test_id, results["plain"])

    # Pass/fail: for ark-only mode, cached plain result doesn't affect status.
    status = "pass"
    for label, r in results.items():
        if not isinstance(r, dict):
            continue
        if mode == "ark-only" and label == "plain":
            continue
        if r.get("exit_code", 0) != 0:
            status = "fail"
            break

    # Token estimation from journal turn counts (500 input + 1500 output per turn).
    _tpt = 500 + 1500
    for label, r in results.items():
        if not isinstance(r, dict):
            continue
        total = sum(e.get("turns", 0) * _tpt for e in r.get("journal_entries", []))
        if label == "architekton":
            r["ark_total_tokens"] = total
        elif label == "plain" and "plain_tokens" not in r:
            r["plain_tokens"] = total

    extra: dict = {
        "token_note": "token counts estimated from journal turn counts (turns * 2000)",
    }
    ark  = results.get("architekton", {})
    plain = results.get("plain", {})
    if isinstance(plain, dict):
        if "ark_total_tokens" in ark and "plain_tokens" in plain:
            extra["overhead_tokens"] = max(0, ark["ark_total_tokens"] - plain["plain_tokens"])
            if ark.get("elapsed_s", 0) > 0 and plain.get("elapsed_s") is not None:
                extra["speedup"] = round(plain["elapsed_s"] / ark["elapsed_s"], 2)

    return {"status": status, "log": str(log_file.relative_to(BENCH_DIR)), **extra, **results}


# ── Report generator ───────────────────────────────────────────────────────────

def generate_per_run_readme(run_dir: Path, manifest: dict) -> Path:
    """Write README.md to run_dir with file inventory and result.json schema."""
    run_id = manifest["run_id"]
    content = f"""\
# architekton benchmark run — {run_id}

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
Actual token usage may differ by \\u00b150% depending on prompt and context length.

## Full benchmark documentation

See `tests/benchmarks/README.md` for the test catalog, category descriptions, and instructions
for adding new tests.
"""
    readme_path = run_dir / "README.md"
    readme_path.write_text(content)
    return readme_path


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mGKHF]")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _extract_tui_snippet(log_content: str, max_lines: int = 25) -> str:
    """Return the final TUI board snapshot from an output log, ANSI codes stripped."""
    clean = _strip_ansi(log_content)
    lines = clean.splitlines()
    # Find the last separator line that precedes a TUI board
    best = 0
    for i, line in enumerate(lines):
        stripped = line.strip("─ -=")
        if not stripped and len(line.strip()) > 20:
            best = i
    snippet = lines[best : best + max_lines]
    while snippet and not snippet[-1].strip():
        snippet.pop()
    return "\n".join(snippet)


def _cat_desc(spec: dict, cat_id: str) -> str:
    for cat in spec.get("categories", []):
        if cat["id"] == cat_id:
            raw = cat.get("description", "").strip().replace("\n", " ")
            return (raw.split(".")[0] + ".") if "." in raw else raw
    return ""


def generate_report(run_dir: Path, manifest: dict) -> Path:
    """Write report.md alongside manifest.json. Renders on GitHub; no tooling needed."""
    try:
        spec = _load_yaml(TESTS_FILE)
    except SystemExit:
        spec = {}

    run_id   = manifest["run_id"]
    mode     = manifest["mode"]
    started  = manifest.get("started_at", "")
    finished = manifest.get("finished_at", "")
    dry_run  = manifest.get("dry_run", False)

    date_str = started[:10] if started else ""
    time_str = started[11:16] if len(started) > 15 else ""
    duration_str = ""
    try:
        t0 = datetime.fromisoformat(started)
        t1 = datetime.fromisoformat(finished)
        secs = (t1 - t0).total_seconds()
        duration_str = f"{secs:.1f}s" if secs < 60 else f"{secs / 60:.1f}m"
    except Exception:
        pass

    test_entries = manifest.get("tests", [])
    passed  = sum(1 for t in test_entries if t["status"] == "pass")
    failed  = sum(1 for t in test_entries if t["status"] == "fail")
    skipped = sum(1 for t in test_entries if t["status"] in ("skipped", "dry-run"))
    errored = sum(1 for t in test_entries if t["status"] in ("error", "interrupted"))

    L: list[str] = []

    L.append("# architekton benchmark report\n")

    meta = f"**Run:** `{run_id}`"
    if date_str:
        meta += f" &nbsp; **Date:** {date_str} {time_str}"
    meta += f" &nbsp; **Mode:** {mode}"
    if duration_str:
        meta += f" &nbsp; **Duration:** {duration_str}"
    if dry_run:
        meta += " &nbsp; *(dry run)*"
    L.append(meta + "\n")
    L.append("---\n")

    summary_parts = []
    if passed:  summary_parts.append(f"**{passed} passed**")
    if failed:  summary_parts.append(f"**{failed} failed**")
    if skipped: summary_parts.append(f"{skipped} skipped")
    if errored: summary_parts.append(f"{errored} errored")
    L.append((" · ".join(summary_parts) or "no results") + "\n")
    L.append("---\n")

    # Group by category, preserving manifest order
    by_cat: dict[str, list[dict]] = {}
    for entry in test_entries:
        t_dir_rel = entry.get("dir", "")
        t_dir = run_dir / t_dir_rel if t_dir_rel else None
        result: dict = {}
        if t_dir and (t_dir / "result.json").exists():
            try:
                result = json.loads((t_dir / "result.json").read_text())
            except Exception:
                pass
        result.setdefault("id", entry["id"])
        result.setdefault("category", entry.get("category", ""))
        result.setdefault("status", entry["status"])
        result["_dir"] = t_dir
        by_cat.setdefault(entry.get("category", "other"), []).append(result)

    for cat, results in by_cat.items():
        L.append(f"## {cat.replace('_', ' ').title()}\n")
        desc = _cat_desc(spec, cat)
        if desc:
            L.append(f"> {desc}\n")

        if cat == "classification":
            L.append("| ID | Test | Expected | Selected | Score | Result | Time |")
            L.append("|----|------|----------|----------|-------|--------|------|")
            for r in results:
                tid      = r.get("id", "?")
                name     = r.get("name", "")
                expected = r.get("expected", "")
                selected = r.get("selected_model", "")
                score    = ""
                try:
                    score = str(json.loads(r.get("stdout", "{}")).get("score", ""))
                except Exception:
                    pass
                status  = r.get("status", "?")
                icon    = "✓" if status == "pass" else ("✗" if status == "fail" else "·")
                elapsed = f"{r['elapsed_s']:.2f}s" if "elapsed_s" in r else "--"
                L.append(
                    f"| {tid} | {name} | {expected} | {selected} | {score} | {icon} | {elapsed} |"
                )

        else:
            has_sub = any("architekton" in r or "plain" in r for r in results)
            if has_sub:
                L.append("| ID | Test | | architekton | plain | Speedup |")
                L.append("|----|------|-|-------------|-------|---------|")
                for r in results:
                    tid    = r.get("id", "?")
                    name   = r.get("name", "")
                    ark    = r.get("architekton", {})
                    pl     = r.get("plain", {})
                    ark_t  = ark.get("elapsed_s")
                    pl_t   = pl.get("elapsed_s")
                    ark_s  = f"{ark_t:.1f}s" if ark_t is not None else "--"
                    pl_s   = f"{pl_t:.1f}s"  if pl_t  is not None else "--"
                    spdup  = (f"{pl_t / ark_t:.1f}×" if ark_t and pl_t and ark_t > 0 else "--")
                    ok     = "✓" if ark.get("exit_code", 1) == 0 else "✗"
                    L.append(f"| {tid} | {name} | {ok} | {ark_s} | {pl_s} | {spdup} |")
            else:
                L.append("| ID | Test | Wall time | Status |")
                L.append("|----|------|-----------|--------|")
                for r in results:
                    tid    = r.get("id", "?")
                    name   = r.get("name", "")
                    status = r.get("status", "?")
                    icon   = "✓" if status == "pass" else ("✗" if status == "fail" else "·")
                    elapsed = "--"
                    for label in ("architekton", "plain"):
                        sub = r.get(label, {})
                        if "elapsed_s" in sub:
                            elapsed = f"{sub['elapsed_s']:.1f}s"
                            break
                    if elapsed == "--" and "elapsed_s" in r:
                        elapsed = f"{r['elapsed_s']:.1f}s"
                    L.append(f"| {tid} | {name} | {elapsed} | {icon} {status} |")

            # TUI snippet from output.log
            for r in results:
                t_dir = r.get("_dir")
                if not t_dir:
                    continue
                log_path = Path(t_dir) / "output.log"
                if not log_path.exists():
                    continue
                snippet = _extract_tui_snippet(log_path.read_text(errors="replace"))
                if snippet:
                    L.append(f"\n### {r.get('id', '?')} — session output\n")
                    L.append("```")
                    L.append(snippet)
                    L.append("```\n")

        L.append("")

    L.append("---")
    L.append("*Generated by architekton benchmark runner*")

    report_path = run_dir / "report.md"
    report_path.write_text("\n".join(L) + "\n")
    return report_path


# ── Run orchestration ──────────────────────────────────────────────────────────

COST_WARNING_THRESHOLD = 2  # number of costly tests before prompting

def _prompt_continue(pending: list[dict]) -> bool:
    """Warn the user and ask for confirmation before running costly tests."""
    costly = [t for t in pending if "$" in t.get("cost_note", "")]
    if not costly:
        return True
    total = len(costly)
    print(f"\nAbout to run {total} test(s) that may incur API costs:")
    for t in costly[:5]:
        print(f"  {t['id']:6}  {t['name']:<45}  {t.get('cost_note','')}")
    if total > 5:
        print(f"  ... and {total-5} more")
    answer = input("\nProceed? [Y/n]: ").strip().lower()
    return answer in ("", "y", "yes")


def run_all(tests: list[dict], mode: str, run_dir: Path, dry_run: bool, real_claude: str,
            save_baseline: bool = False, baseline_from: Path | None = None):
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "run_id": run_dir.name,
        "mode": mode,
        "started_at": datetime.now().isoformat(),
        "dry_run": dry_run,
        "tests": [],
    }

    timing_history = _load_timing_history()
    total = len(tests)
    for i, test in enumerate(tests, 1):
        tid = test["id"]
        cat = test["category"]
        print(f"\n[{i}/{total}]  {tid}  {cat}  --  {test['name']}")
        eta = _eta_info(tid, mode, timing_history)
        if eta:
            print(f"        {eta}")

        test_dir = run_dir / cat / f"{tid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        test_dir.mkdir(parents=True, exist_ok=True)
        result_file = test_dir / "result.json"

        t_start = time.monotonic()
        try:
            if cat == "classification":
                result = _run_classify(test, mode, test_dir, dry_run)
            else:
                result = _run_job(
                    test, mode, test_dir, dry_run, real_claude,
                    test_id=tid, save_baseline=save_baseline, baseline_from=baseline_from,
                )
        except KeyboardInterrupt:
            print(f"\n  Interrupted -- skipping {tid}")
            result = {"status": "interrupted"}
        except Exception as exc:
            print(f"  ERROR: {exc}")
            result = {"status": "error", "error": str(exc)}

        elapsed_wall = time.monotonic() - t_start
        if not dry_run and result.get("status") not in ("dry-run", "interrupted", "error", "skipped"):
            _record_timing(tid, mode, elapsed_wall)
            timing_history = _load_timing_history()

        result["id"] = tid
        result["name"] = test["name"]
        result["category"] = cat
        result["cost_note"] = test.get("cost_note", "")
        result_file.write_text(json.dumps(result, indent=2))

        status = result.get("status", "?")
        icon = {"pass": "PASS", "fail": "FAIL", "skipped": "SKIP", "seeded": "SEED",
                "dry-run": "DRY", "error": "ERR", "interrupted": "INT"}.get(status, status)
        print(f"  [{icon}]", end="")
        if "elapsed_s" in result:
            print(f"  {result['elapsed_s']:.1f}s", end="")
        if "architekton" in result and isinstance(result["architekton"], dict):
            a = result["architekton"]
            p = result.get("plain", {})
            if "elapsed_s" in a:
                print(f"  architekton={a['elapsed_s']:.1f}s", end="")
            if isinstance(p, dict) and "elapsed_s" in p:
                print(f"  plain={p['elapsed_s']:.1f}s", end="")
        print()

        manifest["tests"].append({
            "id": tid,
            "category": cat,
            "status": status,
            "dir": str(test_dir.relative_to(run_dir)),
        })

    manifest["finished_at"] = datetime.now().isoformat()
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    report_path = generate_report(run_dir, manifest)
    generate_per_run_readme(run_dir, manifest)
    print(f"\nResults written to: {run_dir.relative_to(BENCH_DIR)}/")
    print(f"Report:             {report_path.relative_to(BENCH_DIR)}")
    return manifest


# ── Summary ────────────────────────────────────────────────────────────────────

def summarize(run_dirs: list[Path]):
    """Print a comparison table from one or more run directories."""
    all_results: dict[str, list[dict]] = {}  # test_id -> [result_per_run]

    for run_dir in run_dirs:
        # Current layout: <run>/<category>/<test>_<stamp>/result.json.
        # Flat <run>/<test>.json from earlier runs is still read.
        result_files = sorted(run_dir.glob("*/*/result.json")) + sorted(run_dir.glob("*.json"))
        for f in result_files:
            if f.name == "manifest.json":
                continue
            try:
                data = json.loads(f.read_text())
                tid = data.get("id", f.stem)
                all_results.setdefault(tid, []).append(data)
            except (json.JSONDecodeError, OSError):
                pass

    if not all_results:
        print("No result files found.")
        return

    print(f"\n{'ID':<8} {'Category':<18} {'Status':<8} {'Time (s)':<12} {'Notes'}")
    print("-" * 70)
    for tid, runs in sorted(all_results.items()):
        for run in runs:
            status = run.get("status", "?")
            cat = run.get("category", "")
            # Gather timing from either direct or mode-specific fields
            times = []
            for label in ("architekton", "plain"):
                sub = run.get(label, {})
                if "elapsed_s" in sub:
                    times.append(f"{label}={sub['elapsed_s']:.1f}s")
            if "elapsed_s" in run:
                times.append(f"{run['elapsed_s']:.1f}s")
            time_str = "  ".join(times) if times else "--"

            # Cost journal summary
            notes_parts = []
            for label in ("architekton", "plain"):
                entries = run.get(label, {}).get("journal_entries", [])
                if entries:
                    models = {e.get("model", "?") for e in entries}
                    notes_parts.append(f"{label}:{'/'.join(sorted(models))}")
            if run.get("selected_model"):
                notes_parts.append(f"selected:{run['selected_model']}")
            notes = "  ".join(notes_parts)

            print(f"{tid:<8} {cat:<18} {status:<8} {time_str:<12} {notes}")


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="architekton benchmark runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Usage")[1] if "Usage" in __doc__ else "",
    )
    parser.add_argument(
        "--mode",
        choices=["architekton", "plain", "both", "ark-only"],
        default=None,
        help=(
            "architekton: use the job runner (default when wrapper is on PATH). "
            "plain: bypass architekton, call real claude directly. "
            "both: run each test twice and compare. "
            "ark-only: run architekton and load cached plain baseline for comparison."
        ),
    )
    parser.add_argument(
        "--category", metavar="CATEGORY",
        help="run only tests in this category (e.g. parallel_jobs, classification)",
    )
    parser.add_argument(
        "--test", metavar="ID", nargs="+",
        help="run only specific test(s) by ID (e.g. P01 P02 T03)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="show what would run without actually running anything",
    )
    parser.add_argument(
        "--yes", "-y", action="store_true",
        help="skip the cost-confirmation prompt",
    )
    parser.add_argument(
        "--save-baseline", action="store_true",
        help=(
            "save plain results to results/.baseline/<test_id>.json after each plain run. "
            "With --baseline-from, seeds from an existing run without re-running anything."
        ),
    )
    parser.add_argument(
        "--baseline-from", metavar="RUN_ID",
        help=(
            "run ID of an existing results directory (e.g. 20261127_225643). "
            "With --mode plain --save-baseline: seeds .baseline/ from that run, no API calls. "
            "With --mode ark-only: uses that run as the plain comparison source."
        ),
    )
    parser.add_argument(
        "--output", metavar="DIR", default=None,
        help="write results to this directory (default: results/YYYYMMDD_HHMMSS/)",
    )
    parser.add_argument(
        "--summarize", metavar="DIR", nargs="+",
        help="print a summary table from previous run directories and exit",
    )
    args = parser.parse_args()

    # Summarize mode: just print and exit.
    if args.summarize:
        summarize([Path(d) for d in args.summarize])
        return

    # Load tests.
    spec = _load_yaml(TESTS_FILE)
    all_tests = spec.get("tests", [])

    # Determine mode.
    if args.mode is None:
        # Auto-detect: if the architekton wrapper is on PATH, default to architekton.
        wrapper = Path(os.environ.get("HOME", "")) / "bin" / "claude"
        if wrapper.exists():
            try:
                content = wrapper.read_text(errors="ignore")
                if "architekton-wrapper" in content:
                    args.mode = "architekton"
            except OSError:
                pass
        if args.mode is None:
            args.mode = "plain"
            print(
                "Note: architekton wrapper not detected on PATH. "
                "Defaulting to --mode plain.\n"
                "To use architekton, run scripts/install.sh first."
            )

    # Find real claude path (needed even in architekton mode for --mode both).
    real_claude = os.environ.get("REAL_CLAUDE") or _find_real_claude()

    # Filter tests.
    selected = all_tests
    if args.category:
        selected = [t for t in selected if t.get("category") == args.category]
        if not selected:
            known = sorted({t["category"] for t in all_tests})
            sys.exit(f"No tests in category '{args.category}'. Known: {known}")
    if args.test:
        ids = set(args.test)
        selected = [t for t in selected if t.get("id") in ids]
        not_found = ids - {t["id"] for t in selected}
        if not_found:
            sys.exit(f"Test ID(s) not found: {sorted(not_found)}")

    if not selected:
        sys.exit("No tests matched the given filters.")

    print(f"Mode:   {args.mode}")
    print(f"Tests:  {len(selected)}")
    if args.category:
        print(f"Filter: category={args.category}")
    if args.test:
        print(f"Filter: test={args.test}")

    # Cost confirmation.
    if not args.dry_run and not args.yes:
        costly = [t for t in selected if "$" in t.get("cost_note", "")]
        if len(costly) > COST_WARNING_THRESHOLD:
            if not _prompt_continue(selected):
                print("Aborted.")
                return

    # Resolve --baseline-from to an absolute path.
    baseline_from_path: Path | None = None
    if args.baseline_from:
        baseline_from_path = RESULTS_DIR / args.baseline_from
        if not baseline_from_path.exists():
            sys.exit(f"Baseline source not found: {baseline_from_path}")

    # Prepare output directory.
    if args.output:
        run_dir = Path(args.output)
    else:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = RESULTS_DIR / run_id

    # Run.
    manifest = run_all(
        selected, args.mode, run_dir, args.dry_run, real_claude,
        save_baseline=args.save_baseline,
        baseline_from=baseline_from_path,
    )

    passed  = sum(1 for t in manifest["tests"] if t["status"] == "pass")
    failed  = sum(1 for t in manifest["tests"] if t["status"] == "fail")
    skipped = sum(1 for t in manifest["tests"] if t["status"] in ("skipped", "dry-run", "seeded"))
    seeded  = sum(1 for t in manifest["tests"] if t["status"] == "seeded")
    parts   = [f"{passed} passed", f"{failed} failed", f"{skipped} skipped"]
    if seeded:
        parts.append(f"{seeded} baseline seeded")
    print(f"\nSummary: {', '.join(parts)}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
