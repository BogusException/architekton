"""Parallel task runner with a live ANSI TUI."""

import os
import re
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Status(str, Enum):
    WAITING  = "waiting"
    RUNNING  = "running"
    COMPLETE = "complete"
    ERROR    = "error"
    SKIPPED  = "skipped"


@dataclass
class Task:
    id: str
    title: str
    prompt: str
    model: str = "haiku"
    depends_on: list = field(default_factory=list)
    thinking: str = field(default="")   # effort label: "low"|"med"|"high"|"ext"|"" (derived from model)
    timeout: float = field(default=0)   # worker_timeout for display; 0 = no limit shown
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
_R        = "\033[0m"
_RESET_FG = "\033[39m"   # reset fg only, keeps row background active
_BOLD     = "\033[1m"
_DIM      = "\033[2m"
_CYAN     = "\033[36m"
_GREEN    = "\033[32m"
_RED      = "\033[31m"
_YELLOW   = "\033[33m"
_CLRLINE  = "\033[2K\r"
_SPINNER  = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

_STATUS_STYLE = {
    Status.WAITING:  ("·", _DIM),
    Status.RUNNING:  ("⠋", _CYAN),
    Status.COMPLETE: ("✓", _GREEN),
    Status.ERROR:    ("✗", _RED),
    Status.SKIPPED:  ("↷", _YELLOW),
}

# Palette color name -> ANSI escape mappings
_ANSI_FG = {
    "black":          "\033[30m",
    "red":            "\033[31m",
    "green":          "\033[32m",
    "yellow":         "\033[33m",
    "blue":           "\033[34m",
    "magenta":        "\033[35m",
    "cyan":           "\033[36m",
    "white":          "\033[37m",
    "bright_black":   "\033[90m",
    "bright_red":     "\033[91m",
    "bright_green":   "\033[92m",
    "bright_yellow":  "\033[93m",
    "bright_blue":    "\033[94m",
    "bright_magenta": "\033[95m",
    "bright_cyan":    "\033[96m",
    "bright_white":   "\033[97m",
    "dim":            "\033[2m",
    "bold":           "\033[1m",
}
_ANSI_BG = {
    "black":          "\033[40m",
    "red":            "\033[41m",
    "green":          "\033[42m",
    "yellow":         "\033[43m",
    "blue":           "\033[44m",
    "magenta":        "\033[45m",
    "cyan":           "\033[46m",
    "white":          "\033[47m",
    "bright_black":   "\033[100m",
    "bright_red":     "\033[101m",
    "bright_green":   "\033[102m",
    "bright_yellow":  "\033[103m",
    "bright_blue":    "\033[104m",
    "bright_magenta": "\033[105m",
    "bright_cyan":    "\033[106m",
    "bright_white":   "\033[107m",
}
_RGB_RE = re.compile(r"^rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)$", re.I)


def _ansi_fg(spec):
    """Return ANSI fg escape for a color spec: named color, 'rgb(R,G,B)', or ''."""
    s = (spec or "").strip().lower()
    if not s or s == "none":
        return ""
    m = _RGB_RE.match(s)
    if m:
        return f"\033[38;2;{m.group(1)};{m.group(2)};{m.group(3)}m"
    return _ANSI_FG.get(s, "")


def _ansi_bg(spec):
    """Return ANSI bg escape for a color spec: named color, 'rgb(R,G,B)', or ''."""
    s = (spec or "").strip().lower()
    if not s or s == "none":
        return ""
    m = _RGB_RE.match(s)
    if m:
        return f"\033[48;2;{m.group(1)};{m.group(2)};{m.group(3)}m"
    return _ANSI_BG.get(s, "")


def _colorize(text, fg_spec, end=None):
    """Wrap text with an ANSI fg color. Defaults to full reset at end."""
    fg = _ansi_fg(fg_spec)
    if not fg:
        return text
    return f"{fg}{text}{_R if end is None else end}"


class _Palette:
    """Maps tui config color names to ANSI sequences for the job runner TUI."""

    _STATUS_KEYS = {
        Status.WAITING:  "status_waiting",
        Status.RUNNING:  "status_running",
        Status.COMPLETE: "status_complete",
        Status.ERROR:    "status_error",
        Status.SKIPPED:  "status_skipped",
    }

    def __init__(self, cfg, enabled):
        self._cfg = cfg or {}
        self.enabled = bool(enabled)

    def status_fg(self, status):
        return self._cfg.get(self._STATUS_KEYS.get(status, ""), "")

    def model_fg(self, model_str):
        display = _model_display(model_str).lower()
        for family in ("haiku", "sonnet", "opus"):
            if family in display:
                return self._cfg.get(f"model_{family}", "")
        return self._cfg.get("model_other", "")

    def sep_fg(self):
        return self._cfg.get("separator", "")

    def row_bg(self):
        return self._cfg.get("row_bg", "")

    def colorize(self, text, fg_spec, end=None):
        if not self.enabled:
            return text
        return _colorize(text, fg_spec, end=end)

_KNOWN_FAMILIES = {"haiku", "sonnet", "opus"}
_DEFAULT_THINKING_MAP = {"haiku": "low", "sonnet": "med", "opus": "high"}

_VALID_THINKING = frozenset({"low", "med", "high", "ext"})

_THINKING_ALIASES = {
    "medium":   "med",
    "normal":   "med",
    "moderate": "med",
    "minimal":  "low",
    "minimum":  "low",
    "extreme":  "ext",
    "max":      "ext",
    "maximum":  "ext",
    "extended": "ext",
    "ultra":    "ext",
}


def _normalize_thinking(label):
    """Normalize a thinking effort label to a known value.

    Returns (normalized_label, warning_or_None).
    Empty input passes through without warning (means 'derive from model').
    Valid labels pass through unchanged. Aliases are silently corrected.
    Unknown labels pass through with a warning so the display still works.
    """
    if not label:
        return label, None
    low = label.lower()
    if low in _VALID_THINKING:
        return low, None
    if low in _THINKING_ALIASES:
        normalized = _THINKING_ALIASES[low]
        return normalized, f"thinking level '{label}' normalized to '{normalized}'"
    return label, (
        f"unknown thinking level '{label}'; "
        f"valid values: {', '.join(sorted(_VALID_THINKING))}. "
        f"Common aliases: medium=med, extreme/max=ext."
    )


def _model_display(model_str):
    """Convert a model string to a short 'family version' display form.

    'haiku'                      -> 'haiku'
    'claude-opus-4-7'            -> 'opus 4.7'
    'claude-haiku-4-5-20251001'  -> 'haiku 4.5'
    """
    s = model_str.lower()
    if s.startswith("claude-"):
        s = s[7:]
    parts = s.split("-")
    family = None
    ver = []
    for p in parts:
        if family is None:
            if p in _KNOWN_FAMILIES:
                family = p
        elif p.isdigit() and len(p) <= 3:
            ver.append(p)
    if family is None:
        return model_str[:15]
    return f"{family} {'.'.join(ver)}" if ver else family


def _resolve_thinking(task, thinking_map=None):
    """Return the thinking effort label (uses task.thinking if set, else derives from model)."""
    if task.thinking:
        normalized, warning = _normalize_thinking(task.thinking)
        if warning:
            print(f"[auto-brain] {warning}", file=sys.stderr)
        if normalized:
            return normalized
    tmap = thinking_map or _DEFAULT_THINKING_MAP
    s = task.model.lower()
    for family, effort in tmap.items():
        if family in s:
            return effort
    return "med"


def _resolve_thinking_for_model(model_str, thinking_map=None):
    """Derive thinking effort label from a model string (no Task needed)."""
    tmap = thinking_map or _DEFAULT_THINKING_MAP
    s = model_str.lower()
    for family, effort in tmap.items():
        if family in s:
            return effort
    return "med"


def _time_field(task):
    """Format elapsed/timeout display for a task row."""
    if task.status == Status.RUNNING and task.start_time is not None:
        elapsed = time.monotonic() - task.start_time
        if task.timeout > 0:
            return f"{elapsed:.0f}s/{task.timeout:.0f}s"
        return f"{elapsed:.1f}s"
    if task.duration is not None:
        if task.status == Status.ERROR and task.error and "timeout" in task.error.lower():
            return "TIMEOUT"
        return f"{task.duration:.1f}s"
    return "--"


def _term_width():
    try:
        return os.get_terminal_size().columns
    except OSError:
        return 80


class _TUI:
    # Fixed column widths (chars, excluding ANSI codes):
    # status(5) + wid(6) + model(17) + thinking(8) + sep(2) + time(10) = 48
    _FIXED = 48

    def __init__(self, is_tty, thinking_map=None, palette=None, show_orchestrator=True):
        self._is_tty = is_tty
        self._lines = 0
        self._thinking_map = thinking_map
        self._palette = palette
        self._show_orchestrator = show_orchestrator

    def render(self, tasks, job_title, omodel, tick, ostart_time=None, oend_time=None):
        w = _term_width()
        pal = self._palette
        sep_plain = "─" * w
        sep = pal.colorize(sep_plain, pal.sep_fg()) if (pal and pal.enabled) else sep_plain
        counts = {s: sum(1 for t in tasks if t.status == s) for s in Status}
        parts = [
            f"{counts[s]} {s.value}"
            for s in (Status.COMPLETE, Status.RUNNING, Status.WAITING, Status.SKIPPED, Status.ERROR)
            if counts[s]
        ]
        summary = " · ".join(parts)
        omodel_disp = _model_display(omodel)
        title_clip = job_title[: max(w - 30, 10)]
        header = [
            sep,
            f"{_BOLD}auto-brain{_R}  \"{title_clip}\"  {omodel_disp} → workers",
            sep,
        ]
        title_w = max(w - self._FIXED, 15)
        rows = []
        if self._show_orchestrator:
            oicon, odefault_color = _STATUS_STYLE[Status.COMPLETE]
            othinking = _resolve_thinking_for_model(omodel, self._thinking_map)
            omodel_disp = _model_display(omodel)
            if ostart_time is not None:
                end = oend_time if oend_time is not None else time.monotonic()
                odur = end - ostart_time
                otime_str = f"{odur:.1f}s"
            else:
                otime_str = ""
            otitle = f"orchestrator  ({len(tasks)} tasks planned)"
            otitle_trunc = otitle[:title_w]
            if pal and pal.enabled:
                rb_code = _ansi_bg(pal.row_bg())
                field_end = _RESET_FG if rb_code else _R
                sfg = pal.status_fg(Status.COMPLETE)
                mfg = pal.model_fg(omodel)
                icon_c = pal.colorize(oicon, sfg, end=field_end)
                wid_c  = pal.colorize(f"{'orch':<4}", sfg, end=field_end)
                mod_c  = pal.colorize(f"{omodel_disp:<15}", mfg, end=field_end)
                body = (
                    f"  {icon_c}  {wid_c}  {mod_c}  "
                    f"[{othinking:<4}]  {otitle_trunc:<{title_w}}  {otime_str:>10}"
                )
                rows.append(f"{rb_code}{body}{_R}" if rb_code else body)
            else:
                rows.append(
                    f"  {odefault_color}{oicon}{_R}  "
                    f"{'orch':<4}  "
                    f"{omodel_disp:<15}  "
                    f"[{othinking:<4}]  "
                    f"{otitle_trunc:<{title_w}}  "
                    f"{otime_str:>10}"
                )
        for task in tasks:
            icon, default_color = _STATUS_STYLE[task.status]
            if task.status == Status.RUNNING:
                icon = _SPINNER[tick % len(_SPINNER)]
            wid = f"W{task.id}"
            model_disp = _model_display(task.model)
            thinking = _resolve_thinking(task, self._thinking_map)
            time_str = _time_field(task)
            title_trunc = task.title[:title_w]

            if pal and pal.enabled:
                # Pad plain-text fields to fixed widths first (ANSI codes have zero visual width),
                # then wrap with color. This keeps column alignment correct.
                rb_code = _ansi_bg(pal.row_bg())
                field_end = _RESET_FG if rb_code else _R
                sfg = pal.status_fg(task.status)
                mfg = pal.model_fg(task.model)
                icon_c = pal.colorize(icon, sfg, end=field_end)
                wid_c  = pal.colorize(f"{wid:<4}", sfg, end=field_end)
                mod_c  = pal.colorize(f"{model_disp:<15}", mfg, end=field_end)
                body = (
                    f"  {icon_c}  {wid_c}  {mod_c}  "
                    f"[{thinking:<4}]  {title_trunc:<{title_w}}  {time_str:>10}"
                )
                rows.append(f"{rb_code}{body}{_R}" if rb_code else body)
            else:
                rows.append(
                    f"  {default_color}{icon}{_R}  "
                    f"{wid:<4}  "
                    f"{model_disp:<15}  "
                    f"[{thinking:<4}]  "
                    f"{title_trunc:<{title_w}}  "
                    f"{time_str:>10}"
                )
        footer = [sep, summary]
        all_lines = header + rows + footer

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

    def final(self, tasks, job_title, omodel, tick, ostart_time=None, oend_time=None):
        self._lines = 0
        self.render(tasks, job_title, omodel, tick, ostart_time=ostart_time, oend_time=oend_time)


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
        f.write(f"model: {task.model}  thinking: {task.thinking or '(derived)'}  status: {task.status.value}\n\n")
        f.write(stdout)
        if stderr.strip():
            f.write(f"\n=== stderr ===\n{stderr}")


def run(tasks, real_claude, max_parallel=4, worker_timeout=300, worker_max_turns=20,
        job_title="", omodel="opus", cwd=None, output_dir=None, thinking_map=None,
        color_cfg=None, ostart_time=None, oend_time=None):
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
    cfg = color_cfg or {}
    palette = _Palette(cfg, enabled=is_tty and cfg.get("color", True) is not False)
    show_orch = cfg.get("show_orchestrator", True)
    tui = _TUI(is_tty, thinking_map=thinking_map, palette=palette, show_orchestrator=show_orch)
    shutdown = threading.Event()
    threads = []
    tick = 0

    original_sigint = signal.getsignal(signal.SIGINT)

    def _handle_sigint(signum, frame):
        shutdown.set()

    signal.signal(signal.SIGINT, _handle_sigint)
    try:
        tui.render(tasks, job_title, omodel, tick, ostart_time=ostart_time, oend_time=oend_time)

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

            tui.render(tasks, job_title, omodel, tick, ostart_time=ostart_time, oend_time=oend_time)

            if not any(t.status in (Status.WAITING, Status.RUNNING) for t in tasks):
                break

    finally:
        signal.signal(signal.SIGINT, original_sigint)

    for t in threads:
        t.join(timeout=5)

    tui.final(tasks, job_title, omodel, tick, ostart_time=ostart_time, oend_time=oend_time)

    complete = sum(1 for t in tasks if t.status == Status.COMPLETE)
    errors = sum(1 for t in tasks if t.status == Status.ERROR)
    skipped = sum(1 for t in tasks if t.status == Status.SKIPPED)

    if shutdown.is_set():
        print("[auto-brain] Job cancelled.")
    else:
        print(f"\n[auto-brain] Job done: {complete} complete, {errors} error, {skipped} skipped")
        print(f"  Output: {output_dir}")

    return complete, errors, skipped
