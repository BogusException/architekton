"""Decomposes a job description into tasks via an orchestrator model call."""

import json
import os
import subprocess
from pathlib import Path

_DECOMPOSE_PROMPT = """\
You are a task planner for a multi-agent code workflow.
Decompose the job below into atomic tasks for Claude Code agents.

Rules:
- Each task must be completable in one agentic Claude Code session.
- Each task prompt must be fully self-contained (no "as above", no references to other tasks).
- Prefer parallelism; use depends_on only when strict ordering is required.
- Output ONLY a valid JSON array. No prose, no markdown fences.

Model selection guide (default "haiku" unless the task clearly warrants more):
- "haiku"  -- mechanical tasks: single-file edits, rename, format, grep, generate boilerplate
- "sonnet" -- moderate tasks: multi-file edits, analysis across a few files, medium-complexity research
- "opus"   -- complex tasks: test execution, full-codebase reasoning, architectural decisions, synthesis

Thinking effort (optional; omit to let auto-brain derive from model):
- "low"  -- routine mechanical work         (haiku default)
- "med"  -- moderate analysis               (sonnet default)
- "high" -- deep reasoning required         (opus default)
- "ext"  -- maximum effort, use sparingly   (long-running complex tasks only)

Output schema -- a JSON array of objects:
  id:         string, e.g. "1", "2"
  title:      short label (60 chars max)
  prompt:     full instruction for this agent (fully self-contained)
  model:      "haiku" | "sonnet" | "opus"  (see guide above; default "haiku")
  thinking:   "low" | "med" | "high" | "ext"  (optional; omit to derive from model)
  depends_on: list of id strings that must complete first (default [])

Job: {job_description}
"""


def _find_real_claude():
    """Locate the real claude binary, bypassing any auto-brain wrapper."""
    env_path = os.environ.get("AUTO_BRAIN_REAL_CLAUDE", "")
    if env_path and os.access(env_path, os.X_OK):
        return env_path
    brain_home = Path(os.environ.get("CLAUDE_CONFIG_DIR", "") or Path.home() / ".claude") / "smartmodel"
    recorded = brain_home / "real-claude"
    if recorded.is_file():
        path = recorded.read_text(encoding="utf-8").strip()
        if path and os.access(path, os.X_OK):
            return path
    wrapper_path = os.environ.get("AUTO_BRAIN_WRAPPER_PATH", "")
    wrapper_self = Path(wrapper_path).resolve() if wrapper_path else None
    for dir_ in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(dir_) / "claude"
        if not (candidate.is_file() and os.access(candidate, os.X_OK)):
            continue
        if wrapper_self and candidate.resolve() == wrapper_self:
            continue
        return str(candidate)
    return "claude"


def _extract_tasks(text, default_model="haiku"):
    """Parse a JSON task list from LLM output. Handles markdown fences and prose wrappers."""
    text = text.strip()
    if text.startswith("```"):
        lines = [l for l in text.splitlines() if not l.startswith("```")]
        text = "\n".join(lines).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end <= start:
            raise ValueError(f"No JSON array found in orchestrator output:\n{text[:500]}")
        data = json.loads(text[start : end + 1])
    if not isinstance(data, list):
        raise ValueError(f"Orchestrator returned non-list: {type(data).__name__}")
    tasks = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"Task {i} is not an object: {item!r}")
        task_id = item.get("id")
        if not task_id:
            raise ValueError(f"Task {i} is missing required field 'id'")
        prompt = item.get("prompt")
        if not prompt:
            raise ValueError(f"Task {task_id!r} is missing required field 'prompt'")
        tasks.append({
            "id": str(task_id),
            "title": str(item.get("title", task_id))[:60],
            "prompt": str(prompt),
            "model": str(item.get("model") or default_model),
            "thinking": str(item.get("thinking") or ""),
            "depends_on": [str(d) for d in item.get("depends_on") or []],
        })
    return tasks


def decompose(job_description, model="opus", timeout=120, real_claude=None,
              preamble="", default_worker_model="haiku"):
    """Call the orchestrator model and return a validated list of task dicts."""
    if real_claude is None:
        real_claude = _find_real_claude()
    prompt = preamble + _DECOMPOSE_PROMPT.format(job_description=job_description.strip())
    env = {**os.environ, "SMARTMODEL_DISABLE": "1"}
    result = subprocess.run(
        [real_claude, "--print", f"--model={model}", "-p", prompt],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Orchestrator call failed (exit {result.returncode}):\n{result.stderr.strip()}"
        )
    return _extract_tasks(result.stdout, default_model=default_worker_model)
