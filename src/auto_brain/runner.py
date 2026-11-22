"""Parallel task runner with a live ANSI TUI."""

import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Status(str, Enum):
    WAITING = "waiting"
    RUNNING = "running"
    COMPLETE = "complete"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass
class Task:
    id: str
    title: str
    prompt: str
    model: str = "haiku"
    depends_on: list = field(default_factory=list)
    status: Status = field(default=Status.WAITING)
    output: str = field(default="", repr=False)
    error: str = field(default="", repr=False)
    start_time: float = field(default=None, repr=False)
    end_time: float = field(default=None, repr=False)
    proc: object = field(default=None, repr=False, compare=False)

    @property
    def duration(self):
        if self.start_time is None:
            return None
        return (self.end_time if self.end_time is not None else time.monotonic()) - self.start_time


# ANSI codes
_R = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_CLRLINE = "\033[2K\r"
_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

_STATUS_STYLE = {
    Status.WAITING:  ("·", _DIM),
    Status.RUNNING:  ("⠋", _CYAN),
    Status.COMPLETE: ("✓", _GREEN),
    Status.ERROR:    ("✗", _RED),
    Status.SKIPPED:  ("↷", _YELLOW),
}


def _term_width():
    try:
        return os.get_terminal_size().columns
    except OSError:
        return 80


class _TUI:
    def __init__(self, is_tty):
        self._is_tty = is_tty
        self._lines = 0

    def render(self, tasks, job_title, omodel, tick):
        w = _term_width()
        sep = "─" * w
        counts = {s: sum(1 for t in tasks if t.status == s) for s in Status}
        parts = [
            f"{counts[s]} {s.value}"
            for s in (Status.COMPLETE, Status.RUNNING, Status.WAITING, Status.SKIPPED, Status.ERROR)
            if counts[s]
        ]
        summary = " · ".join(parts)
        title_clip = job_title[: max(w - 30, 10)]
        header = [
            sep,
            f"{_BOLD}auto-brain{_R}  {title_clip}  {omodel} → workers",
            summary,
            sep,
        ]
        rows = []
        title_w = max(w - 36, 20)
        for task in tasks:
            icon, color = _STATUS_STYLE[task.status]
            if task.status == Status.RUNNING:
                icon = _SPINNER[tick % len(_SPINNER)]
            dur = f"{task.duration:.1f}s" if task.duration is not None else "  --"
            rows.append(
                f"  {color}{icon}{_R}  {task.id:<3} {task.title[:title_w]:<{title_w}} {task.model[:8]:<8} {dur:>6}"
            )
        all_lines = header + rows + [sep]

        if self._is_tty:
            if self._lines > 0:
                sys.stdout.write(f"\033[{self._lines}A")
            for line in all_lines:
                sys.stdout.write(f"{_CLRLINE}{line}\n")
            sys.stdout.flush()
        else:
            sys.stdout.write(f"[auto-brain] {summary}\n")
            sys.stdout.flush()
        self._lines = len(all_lines)

    def final(self, tasks, job_title, omodel, tick):
        self._lines = 0
        self.render(tasks, job_title, omodel, tick)


def _ready_tasks(tasks):
    """Return WAITING tasks whose dependencies are all COMPLETE."""
    done = {t.id for t in tasks if t.status == Status.COMPLETE}
    return [
        t for t in tasks
        if t.status == Status.WAITING and all(d in done for d in t.depends_on)
    ]


def _has_failed_dep(task, tasks):
    """Return True if any dependency ended in ERROR or SKIPPED."""
    bad = {t.id for t in tasks if t.status in (Status.ERROR, Status.SKIPPED)}
    return any(d in bad for d in task.depends_on)


def _worker(task, real_claude, timeout, max_turns, cwd, output_dir, shutdown):
    """Worker thread: execute one task via claude --print."""
    if shutdown.is_set():
        task.status = Status.SKIPPED
        return
    task.status = Status.RUNNING
    task.start_time = time.monotonic()
    env = {**os.environ, "SMARTMODEL_DISABLE": "1"}
    try:
        proc = subprocess.Popen(
            [real_claude, "--print", f"--model={task.model}",
             f"--max-turns={max_turns}", "-p", task.prompt],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
            env=env,
        )
        task.proc = proc
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            task.status = Status.ERROR
            task.error = f"timeout after {timeout}s"
            task.end_time = time.monotonic()
            task.proc = None
            _write_output(output_dir, task, stdout, stderr)
            return
        task.proc = None
        task.output = stdout
        task.error = stderr
        task.end_time = time.monotonic()
        task.status = Status.COMPLETE if proc.returncode == 0 else Status.ERROR
        _write_output(output_dir, task, stdout, stderr)
    except Exception as exc:
        task.status = Status.ERROR
        task.error = str(exc)
        task.end_time = time.monotonic()
        task.proc = None


def _write_output(output_dir, task, stdout, stderr):
    out_path = Path(output_dir) / f"{task.id}.txt"
    with out_path.open("w", encoding="utf-8") as f:
        f.write(f"=== task {task.id}: {task.title} ===\n")
        f.write(f"model: {task.model}  status: {task.status.value}\n\n")
        f.write(stdout)
        if stderr.strip():
            f.write(f"\n=== stderr ===\n{stderr}")


def run(tasks, real_claude, max_parallel=4, worker_timeout=300, worker_max_turns=20,
        job_title="", omodel="opus", cwd=None, output_dir=None):
    """Execute a task DAG with parallel workers and a live TUI.

    Returns (complete_count, error_count, skipped_count).
    """
    if cwd is None:
        cwd = os.getcwd()
    if output_dir is None:
        output_dir = (
            Path(os.environ.get("CLAUDE_CONFIG_DIR", "") or Path.home() / ".claude")
            / "smartmodel" / "jobs" / "default"
        )
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    is_tty = sys.stdout.isatty()
    tui = _TUI(is_tty)
    shutdown = threading.Event()
    threads = []
    tick = 0

    original_sigint = signal.getsignal(signal.SIGINT)

    def _handle_sigint(signum, frame):
        shutdown.set()

    signal.signal(signal.SIGINT, _handle_sigint)
    try:
        tui.render(tasks, job_title, omodel, tick)

        while True:
            tick += 1
            time.sleep(0.1)

            if shutdown.is_set():
                for task in tasks:
                    if task.proc is not None:
                        try:
                            task.proc.terminate()
                        except OSError:
                            pass
                for task in tasks:
                    if task.status in (Status.WAITING, Status.RUNNING):
                        task.status = Status.SKIPPED
                break

            for task in tasks:
                if task.status == Status.WAITING and _has_failed_dep(task, tasks):
                    task.status = Status.SKIPPED

            running = sum(1 for t in tasks if t.status == Status.RUNNING)
            for task in _ready_tasks(tasks):
                if running >= max_parallel:
                    break
                t = threading.Thread(
                    target=_worker,
                    args=(task, real_claude, worker_timeout, worker_max_turns,
                          cwd, output_dir, shutdown),
                    daemon=True,
                )
                threads.append(t)
                t.start()
                running += 1

            tui.render(tasks, job_title, omodel, tick)

            if not any(t.status in (Status.WAITING, Status.RUNNING) for t in tasks):
                break

    finally:
        signal.signal(signal.SIGINT, original_sigint)

    for t in threads:
        t.join(timeout=5)

    tui.final(tasks, job_title, omodel, tick)

    complete = sum(1 for t in tasks if t.status == Status.COMPLETE)
    errors = sum(1 for t in tasks if t.status == Status.ERROR)
    skipped = sum(1 for t in tasks if t.status == Status.SKIPPED)

    if shutdown.is_set():
        print("[auto-brain] Job cancelled.")
    else:
        print(f"\n[auto-brain] Job done: {complete} complete, {errors} error, {skipped} skipped")
        print(f"  Output: {output_dir}")

    return complete, errors, skipped
