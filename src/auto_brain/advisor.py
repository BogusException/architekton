"""auto-brain CLI: classify, session-start, toggle, status, warn, session-end, report, run."""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from auto_brain import classifier, config, fingerprint, journal, orchestrator, runner


def run_classify(args):
    text = args.text if args.text is not None else sys.stdin.read()
    print(json.dumps(classifier.classify(text, config.load())))
    return 0


def run_session_start(args):
    """Print "model<TAB>source" for the wrapper, or nothing to leave claude alone."""
    cfg = config.load()
    if not config.is_enabled(cfg) or cfg["mode"] == "advisory":
        return 0
    model, source = config.resolve_model()
    if source == "built-in default":
        fp = fingerprint.detect()
        if fp["tier"] is not None:
            model = cfg["models"][fp["tier"]]
            source = f"project-fingerprint ({fp['reason']})"
    print(f"{model}\t{source}")
    return 0


def run_toggle(args):
    if args.state is None:
        should_enable = not config.load()["enabled"]
    else:
        should_enable = args.state == "on"
    config.set_global_enabled(should_enable)
    print(f"auto-brain {'on' if should_enable else 'off'} ({config.get_global_config_path()})")
    return 0


def run_status(args):
    cfg = config.load()
    model, source = config.resolve_model()
    state = "enabled" if config.is_enabled(cfg) else "disabled"
    if cfg["enabled"] and state == "disabled":
        state += " (SMARTMODEL_DISABLE=1)"
    print(f"state:          {state}")
    print(f"mode:           {cfg['mode']}")
    print(f"session model:  {model} ({source})")
    print(f"global config:  {config.get_global_config_path()}")
    print(f"project config: {config.get_project_config_path()}")
    return 0


def run_session_end(args):
    """Stop hook: count turns from transcript, append a journal entry."""
    try:
        payload = json.load(sys.stdin)
        transcript_path = payload.get("transcript_path", "")
        turns = journal._count_turns(transcript_path) if transcript_path else 0
        model = args.model or os.environ.get("AUTO_BRAIN_MODEL") or os.environ.get("CLAUDE_MODEL") or "sonnet"
        journal.session_end(model, turns)
    except Exception as error:
        print(f"auto-brain journal: {error}", file=sys.stderr)
    return 0


def run_report(args):
    cfg = config.load()
    pricing = cfg.get("pricing")
    print(journal.report(days=args.days, pricing=pricing))
    return 0


def run_warn(args):
    """UserPromptSubmit hook. Never blocks a prompt: any failure prints nothing."""
    try:
        cfg = config.load()
        if not config.is_enabled(cfg):
            return 0
        prompt = json.load(sys.stdin).get("prompt", "")
        current = (
            os.environ.get("CLAUDE_MODEL")
            or os.environ.get("AUTO_BRAIN_MODEL")
            or config.resolve_model()[0]
        )
        current_tier = classifier.get_tier_of_model(current)
        result = classifier.classify(prompt, cfg)
        if current_tier is None or result["tier"] == current_tier:
            return 0
        note = (
            f"[auto-brain] Complexity suggests {result['recommended_model']} "
            f"(you are on {current}). Switch: /model {result['recommended_model']}"
        )
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": note}}))
    except Exception as error:
        print(f"auto-brain warn: {error}", file=sys.stderr)
    return 0


_RUN_DESCRIPTION = (
    "Decompose a goal into tasks using an orchestrator model, then execute "
    "them in parallel with worker models and a live status display."
)
_RUN_EPILOG = """\
Model aliases:  haiku, sonnet, opus
Full model IDs: claude-opus-4-7, claude-haiku-4-5-20251001, etc.
Unknown model values emit a warning at startup and will cause workers to fail
if the model is unavailable.

Thinking effort levels:
  low   routine mechanical work         (haiku default)
  med   moderate analysis               (sonnet default)
  high  deep reasoning required         (opus default)
  ext   maximum effort, use sparingly

Common aliases are accepted in config (medium -> med, extreme/max -> ext) but
canonical labels are preferred. Unknown labels emit a warning and pass through.

Config files (project overrides global):
  global:  ~/.claude/smartmodel/config.json
  project: .claude/smartmodel.json

Full config reference: docs/customizing.md, section 1
"""


def run_job(args):
    cfg = config.load()
    job_cfg = cfg.get("job", {})
    # CLI flags override config when explicitly provided (not None)
    omodel       = getattr(args, "orchestrator_model", None) or job_cfg.get("orchestrator_model", "opus")
    wmodel       = getattr(args, "worker_model", None) or job_cfg.get("worker_model", "haiku")
    max_parallel = getattr(args, "max_parallel", None) or job_cfg.get("max_parallel", 4)
    wtimeout     = getattr(args, "timeout", None) or job_cfg.get("worker_timeout", 300)
    wturns       = job_cfg.get("worker_max_turns", 20)
    preamble     = job_cfg.get("orchestrator_preamble", "")
    thinking_map = job_cfg.get("thinking_map", {})
    # CLI --thinking overrides config worker_thinking
    wthinking    = getattr(args, "thinking", None) or job_cfg.get("worker_thinking", "")
    description  = " ".join(args.job)
    real_claude  = orchestrator._find_real_claude()

    import time as _time
    show_orch = cfg.get("tui", {}).get("show_orchestrator", True)
    if not show_orch:
        print(f"[auto-brain] Planning with {omodel}...", file=sys.stderr)
    ostart_time = _time.monotonic()
    try:
        tasks_raw = orchestrator.decompose(
            description, model=omodel, real_claude=real_claude,
            preamble=preamble, default_worker_model=wmodel,
        )
    except Exception as error:
        print(f"auto-brain: orchestrator failed: {error}", file=sys.stderr)
        return 1
    oend_time = _time.monotonic()

    tasks = [
        runner.Task(
            id=t["id"],
            title=t.get("title", t["id"]),
            prompt=t["prompt"],
            model=t.get("model", wmodel),
            depends_on=t.get("depends_on", []),
            thinking=t.get("thinking", "") or wthinking,
            timeout=float(wtimeout),
        )
        for t in tasks_raw
    ]
    if not show_orch:
        print(f"[auto-brain] {len(tasks)} tasks planned.", file=sys.stderr)

    output_dir = (
        Path(os.environ.get("CLAUDE_CONFIG_DIR", "") or Path.home() / ".claude")
        / "smartmodel" / "jobs"
        / datetime.now().strftime("%Y%m%d-%H%M%S")
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    _complete, errors, _skipped = runner.run(
        tasks,
        real_claude=real_claude,
        max_parallel=max_parallel,
        worker_timeout=wtimeout,
        worker_max_turns=wturns,
        job_title=description,
        omodel=omodel,
        output_dir=output_dir,
        thinking_map=thinking_map,
        color_cfg=cfg.get("tui", {}),
        ostart_time=ostart_time,
        oend_time=oend_time,
    )
    return 0 if errors == 0 else 1


def build_parser():
    parser = argparse.ArgumentParser(prog="advisor")
    commands = parser.add_subparsers(dest="command", required=True)

    classify = commands.add_parser("classify", help="score a prompt (reads stdin when TEXT is omitted)")
    classify.add_argument("text", nargs="?")
    classify.set_defaults(run=run_classify)

    session_start = commands.add_parser("session-start", help="print the model the wrapper should launch with")
    session_start.set_defaults(run=run_session_start)

    toggle = commands.add_parser("toggle", help="turn auto-brain on or off globally")
    toggle.add_argument("state", nargs="?", choices=("on", "off"))
    toggle.set_defaults(run=run_toggle)

    status = commands.add_parser("status", help="show current config and session model")
    status.set_defaults(run=run_status)

    warn = commands.add_parser("warn", help="UserPromptSubmit hook entry point (JSON on stdin)")
    warn.set_defaults(run=run_warn)

    session_end = commands.add_parser("session-end", help="Stop hook: append session stats to cost journal (JSON on stdin)")
    session_end.add_argument("--model", default=None, help="override model (default: $AUTO_BRAIN_MODEL or $CLAUDE_MODEL)")
    session_end.set_defaults(run=run_session_end)

    rep = commands.add_parser("report", help="print spend report from the cost journal")
    rep.add_argument("--days", type=int, default=None, metavar="N", help="limit to last N days (default: all time)")
    rep.set_defaults(run=run_report)

    job = commands.add_parser(
        "run",
        help="run a multi-agent job (orchestrator decomposes, workers execute)",
        description=_RUN_DESCRIPTION,
        epilog=_RUN_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    job.add_argument("job", nargs="+", help="job description (quote or space-separate words)")
    job.add_argument(
        "--orchestrator-model", metavar="MODEL", default=None,
        help="model for the planner (overrides config job.orchestrator_model; default: opus). "
             "Accepts alias (haiku/sonnet/opus) or full model ID.",
    )
    job.add_argument(
        "--worker-model", metavar="MODEL", default=None,
        help="default model for workers when orchestrator does not assign one "
             "(overrides config job.worker_model; default: haiku)",
    )
    job.add_argument(
        "--max-parallel", metavar="N", type=int, default=None,
        help="maximum concurrent worker sessions (overrides config job.max_parallel; default: 4)",
    )
    job.add_argument(
        "--timeout", metavar="SEC", type=int, default=None,
        help="seconds before a worker session is killed (overrides config job.worker_timeout; default: 300)",
    )
    job.add_argument(
        "--thinking", metavar="LEVEL", default=None,
        choices=["low", "med", "high", "ext"],
        help="override thinking effort for all workers: low, med, high, ext "
             "(default: derived from each task's model tier via thinking_map config)",
    )
    job.set_defaults(run=run_job)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.run(args)
    except config.ConfigError as error:
        print(f"auto-brain: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
