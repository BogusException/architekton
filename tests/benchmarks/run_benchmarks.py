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

Output
------
Each test run writes:
  results/<run_id>/manifest.json     summary of the whole run
  results/<run_id>/<test_id>.json    per-test result (timing, exit code, notes)
  results/<run_id>/<test_id>.log     raw stdout + stderr from the test

The run_id is a timestamp: YYYYMMDD_HHMMSS.
"""

import argparse
import json
import os
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
RESULTS_DIR = BENCH_DIR / "results"

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


# ── Test runner ────────────────────────────────────────────────────────────────

def _run_classify(test: dict, mode: str, run_dir: Path, dry_run: bool) -> dict:
    """Execute a classification test and return a result dict."""
    prompt = test["prompt"]
    expected = test.get("expected", "")

    if dry_run:
        print(f"  [dry-run] classify: {prompt[:60]}...")
        return {"status": "dry-run", "expected": expected}

    env = {**os.environ, "ARCHITEKTON_PROMPT": prompt}
    advisor = [
        sys.executable, "-m", "architekton.advisor", "session-start",
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
        advisor, capture_output=True, text=True, env=env, cwd=str(REPO_ROOT),
    )
    elapsed = time.monotonic() - start

    selected = result.stdout.strip()
    passed = expected.lower() in selected.lower() if expected else True

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


def _run_job(test: dict, mode: str, run_dir: Path, dry_run: bool, real_claude: str) -> dict:
    """Execute a job test in the requested mode and return a result dict."""
    workdir = str(REPO_ROOT / test.get("workdir", "."))
    log_file = run_dir / f"{test['id']}.log"

    cmds = []
    if mode in ("architekton", "both"):
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

    status = "pass"
    for label, r in results.items():
        if r["exit_code"] != 0:
            status = "fail"
            break

    return {"status": status, "log": str(log_file.relative_to(BENCH_DIR)), **results}


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


def run_all(tests: list[dict], mode: str, run_dir: Path, dry_run: bool, real_claude: str):
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "run_id": run_dir.name,
        "mode": mode,
        "started_at": datetime.now().isoformat(),
        "dry_run": dry_run,
        "tests": [],
    }

    total = len(tests)
    for i, test in enumerate(tests, 1):
        tid = test["id"]
        cat = test["category"]
        print(f"\n[{i}/{total}] {tid} ({cat}) -- {test['name']}")

        result_file = run_dir / f"{tid}.json"

        try:
            if cat == "classification":
                result = _run_classify(test, mode, run_dir, dry_run)
            else:
                result = _run_job(test, mode, run_dir, dry_run, real_claude)
        except KeyboardInterrupt:
            print(f"\n  Interrupted -- skipping {tid}")
            result = {"status": "interrupted"}
        except Exception as exc:
            print(f"  ERROR: {exc}")
            result = {"status": "error", "error": str(exc)}

        result["id"] = tid
        result["name"] = test["name"]
        result["category"] = cat
        result["cost_note"] = test.get("cost_note", "")
        result_file.write_text(json.dumps(result, indent=2))

        status = result.get("status", "?")
        icon = {"pass": "PASS", "fail": "FAIL", "skipped": "SKIP",
                "dry-run": "DRY", "error": "ERR", "interrupted": "INT"}.get(status, status)
        print(f"  [{icon}]", end="")
        if "elapsed_s" in result:
            print(f"  {result['elapsed_s']:.1f}s", end="")
        if "architekton" in result and "elapsed_s" in result["architekton"]:
            a = result["architekton"]
            p = result.get("plain", {})
            print(f"  architekton={a['elapsed_s']:.1f}s", end="")
            if p:
                print(f"  plain={p['elapsed_s']:.1f}s", end="")
        print()

        manifest["tests"].append({"id": tid, "status": status})

    manifest["finished_at"] = datetime.now().isoformat()
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"\nResults written to: {run_dir.relative_to(BENCH_DIR)}/")
    return manifest


# ── Summary ────────────────────────────────────────────────────────────────────

def summarize(run_dirs: list[Path]):
    """Print a comparison table from one or more run directories."""
    all_results: dict[str, list[dict]] = {}  # test_id -> [result_per_run]

    for run_dir in run_dirs:
        for f in sorted(run_dir.glob("*.json")):
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
        choices=["architekton", "plain", "both"],
        default=None,
        help=(
            "architekton: use the job runner (default when wrapper is on PATH). "
            "plain: bypass architekton, call real claude directly. "
            "both: run each test twice and compare."
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

    # Prepare output directory.
    if args.output:
        run_dir = Path(args.output)
    else:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = RESULTS_DIR / run_id

    # Run.
    manifest = run_all(selected, args.mode, run_dir, args.dry_run, real_claude)

    passed = sum(1 for t in manifest["tests"] if t["status"] == "pass")
    failed = sum(1 for t in manifest["tests"] if t["status"] == "fail")
    skipped = sum(1 for t in manifest["tests"] if t["status"] in ("skipped", "dry-run"))
    print(f"\nSummary: {passed} passed, {failed} failed, {skipped} skipped")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
