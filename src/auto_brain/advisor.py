"""auto-brain CLI: classify, session-start, toggle, status, warn, session-end, report."""

import argparse
import json
import os
import sys

from auto_brain import classifier, config, fingerprint, journal


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
        current = os.environ.get("AUTO_BRAIN_MODEL") or os.environ.get("CLAUDE_MODEL")
        current_tier = classifier.get_tier_of_model(current)
        result = classifier.classify(prompt, cfg)
        if current_tier is None or result["tier"] == current_tier:
            return 0
        note = (
            f"[auto-brain] Complexity suggests {result['recommended_model']} "
            f"(you are on {current}). Restart: claude --model {result['recommended_model']}"
        )
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": note}}))
    except Exception as error:
        print(f"auto-brain warn: {error}", file=sys.stderr)
    return 0


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
