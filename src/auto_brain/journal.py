"""Per-session cost journal: append and report."""

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Rough token estimates per turn for cost calculation (input + output).
_TOKENS_IN_PER_TURN = 500
_TOKENS_OUT_PER_TURN = 1500

_DEFAULT_PRICING = {
    "opus":   {"input_per_1m": 15.00, "output_per_1m": 75.00},
    "sonnet": {"input_per_1m":  3.00, "output_per_1m": 15.00},
    "haiku":  {"input_per_1m":  0.80, "output_per_1m":  4.00},
}


def _journal_path():
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return Path(base) / "smartmodel" / "cost-journal.jsonl"


def _tier_for_model(model):
    model = model.lower()
    if "opus" in model:
        return "opus"
    if "haiku" in model:
        return "haiku"
    return "sonnet"


def session_end(model, turns, heavy_prompts=0, light_prompts=0):
    """Append one journal entry for the completed session."""
    path = _journal_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "date": datetime.now(timezone.utc).isoformat(),
        "project": os.path.basename(os.path.abspath(os.getcwd())),
        "model": model,
        "turns": turns,
        "heavy_prompts": heavy_prompts,
        "light_prompts": light_prompts,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _count_turns(transcript_path):
    """Count user-role messages in a Claude Code transcript JSONL."""
    count = 0
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("message", {}).get("role") == "user":
                        count += 1
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return count


def _read_entries(days=None):
    path = _journal_path()
    if not path.exists():
        return []
    cutoff = None
    if days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    entries = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if cutoff is not None:
                    entry_date = datetime.fromisoformat(entry["date"])
                    if entry_date.tzinfo is None:
                        entry_date = entry_date.replace(tzinfo=timezone.utc)
                    if entry_date < cutoff:
                        continue
                entries.append(entry)
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
    return entries


def report(days=None, pricing=None):
    """Return a formatted spend report string."""
    if pricing is None:
        pricing = _DEFAULT_PRICING
    entries = _read_entries(days)
    period = f"last {days} days" if days is not None else "all time"
    if not entries:
        return f"No journal entries ({period})."

    projects = {}
    for e in entries:
        proj = e.get("project", "unknown")
        if proj not in projects:
            projects[proj] = {"sessions": 0, "turns": 0, "models": {}}
        p = projects[proj]
        p["sessions"] += 1
        p["turns"] += e.get("turns", 0)
        tier = _tier_for_model(e.get("model", "sonnet"))
        p["models"][tier] = p["models"].get(tier, 0) + 1

    header = f"Cost journal  --  {period}  ({len(entries)} sessions, estimated costs)\n"
    col = f"{'project':<30}  {'sessions':>8}  {'turns':>6}  {'model mix':<20}  {'est. cost':>10}"
    sep = "-" * len(col)
    rows = []
    for proj, data in sorted(projects.items()):
        total_sessions = data["sessions"]
        total_turns = data["turns"]
        mix_parts = []
        est = 0.0
        for tier in ("opus", "sonnet", "haiku"):
            count = data["models"].get(tier, 0)
            if count:
                pct = round(count * 100 / total_sessions)
                mix_parts.append(f"{tier[0].upper()}:{pct}%")
                tier_turns = total_turns * count / total_sessions
                p = pricing.get(tier, _DEFAULT_PRICING["sonnet"])
                est += (tier_turns * _TOKENS_IN_PER_TURN / 1_000_000) * p["input_per_1m"]
                est += (tier_turns * _TOKENS_OUT_PER_TURN / 1_000_000) * p["output_per_1m"]
        mix = " ".join(mix_parts) if mix_parts else "unknown"
        rows.append(f"{proj:<30}  {total_sessions:>8}  {total_turns:>6}  {mix:<20}  ${est:>9.2f}")

    return "\n".join([header, col, sep] + rows)
