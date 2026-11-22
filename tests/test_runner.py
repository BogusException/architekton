import io
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from auto_brain.runner import (
    Status, Task, _ready_tasks, _has_failed_dep, _TUI, _write_output, run,
    _model_display, _resolve_thinking, _time_field,
    _normalize_thinking, _VALID_THINKING, _THINKING_ALIASES,
)


def _task(id_, depends_on=None, status=Status.WAITING, model="haiku"):
    t = Task(id=id_, title=f"Task {id_}", prompt=f"do task {id_}", model=model,
             depends_on=depends_on or [])
    t.status = status
    return t


class TaskDagTest(unittest.TestCase):
    def test_waiting_task_no_deps_is_ready(self):
        tasks = [_task("1")]
        self.assertEqual(len(_ready_tasks(tasks)), 1)

    def test_task_with_unsatisfied_dep_is_not_ready(self):
        tasks = [_task("1"), _task("2", depends_on=["1"])]
        ready_ids = {t.id for t in _ready_tasks(tasks)}
        self.assertIn("1", ready_ids)
        self.assertNotIn("2", ready_ids)

    def test_task_becomes_ready_after_dep_completes(self):
        t1 = _task("1", status=Status.COMPLETE)
        t2 = _task("2", depends_on=["1"])
        ready = _ready_tasks([t1, t2])
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0].id, "2")

    def test_running_task_not_in_ready_list(self):
        t1 = _task("1", status=Status.RUNNING)
        self.assertEqual(_ready_tasks([t1]), [])

    def test_failed_dep_triggers_has_failed(self):
        t1 = _task("1", status=Status.ERROR)
        t2 = _task("2", depends_on=["1"])
        self.assertTrue(_has_failed_dep(t2, [t1, t2]))

    def test_skipped_dep_triggers_has_failed(self):
        t1 = _task("1", status=Status.SKIPPED)
        t2 = _task("2", depends_on=["1"])
        self.assertTrue(_has_failed_dep(t2, [t1, t2]))

    def test_independent_task_unaffected_by_unrelated_error(self):
        t1 = _task("1", status=Status.ERROR)
        t2 = _task("2")  # no dependency on t1
        self.assertFalse(_has_failed_dep(t2, [t1, t2]))

    def test_complete_dep_does_not_count_as_failed(self):
        t1 = _task("1", status=Status.COMPLETE)
        t2 = _task("2", depends_on=["1"])
        self.assertFalse(_has_failed_dep(t2, [t1, t2]))


class TaskDurationTest(unittest.TestCase):
    def test_duration_none_before_start(self):
        t = Task(id="1", title="T", prompt="p")
        self.assertIsNone(t.duration)

    def test_duration_running(self):
        t = Task(id="1", title="T", prompt="p")
        t.start_time = time.monotonic() - 1.0
        self.assertGreaterEqual(t.duration, 1.0)

    def test_duration_complete(self):
        t = Task(id="1", title="T", prompt="p")
        t.start_time = 100.0
        t.end_time = 102.5
        self.assertAlmostEqual(t.duration, 2.5, places=5)


class TUITest(unittest.TestCase):
    def _render(self, is_tty=False):
        tasks = []
        for i, s in enumerate(Status):
            t = Task(id=str(i), title=f"Task {i}", prompt="x")
            t.status = s
            if s == Status.RUNNING:
                t.start_time = time.monotonic()
            tasks.append(t)
        tui = _TUI(is_tty=is_tty)
        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            tui.render(tasks, "test job", "opus", tick=3)
        return buf.getvalue()

    def test_renders_without_crash_non_tty(self):
        output = self._render(is_tty=False)
        self.assertIn("auto-brain", output)

    def test_renders_without_crash_tty(self):
        output = self._render(is_tty=True)
        # Should contain status indicators
        self.assertIn("✓", output)
        self.assertIn("✗", output)

    def test_non_tty_prints_summary_line(self):
        output = self._render(is_tty=False)
        self.assertIn("[auto-brain]", output)

    def test_final_forces_full_redraw(self):
        tui = _TUI(is_tty=False)
        tui._lines = 999  # simulate having drawn before
        tasks = [Task(id="1", title="T", prompt="p", status=Status.COMPLETE)]
        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            tui.final(tasks, "job", "opus", tick=0)
        self.assertEqual(tui._lines, len(tasks) + 5)  # sep + title + sep + rows + sep + summary


class WriteOutputTest(unittest.TestCase):
    def test_writes_output_file(self):
        tmp = tempfile.mkdtemp()
        t = Task(id="1", title="My Task", prompt="p", status=Status.COMPLETE)
        _write_output(tmp, t, "output text", "")
        content = (Path(tmp) / "1.txt").read_text()
        self.assertIn("My Task", content)
        self.assertIn("output text", content)

    def test_writes_stderr_when_present(self):
        tmp = tempfile.mkdtemp()
        t = Task(id="1", title="T", prompt="p", status=Status.ERROR)
        _write_output(tmp, t, "", "some error")
        content = (Path(tmp) / "1.txt").read_text()
        self.assertIn("some error", content)

    def test_skips_stderr_section_when_empty(self):
        tmp = tempfile.mkdtemp()
        t = Task(id="1", title="T", prompt="p", status=Status.COMPLETE)
        _write_output(tmp, t, "clean output", "")
        content = (Path(tmp) / "1.txt").read_text()
        self.assertNotIn("stderr", content)


class RunIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _fake_worker(self, result_status=Status.COMPLETE, delay=0.02):
        def worker(task, real_claude, timeout, max_turns, cwd, output_dir, shutdown):
            time.sleep(delay)
            task.status = result_status
            task.start_time = time.monotonic() - delay
            task.end_time = time.monotonic()
            Path(output_dir, f"{task.id}.txt").write_text("ok")
        return worker

    def test_all_complete(self):
        tasks = [Task(id="1", title="T1", prompt="p1"), Task(id="2", title="T2", prompt="p2")]
        with mock.patch("auto_brain.runner._worker", side_effect=self._fake_worker()):
            with mock.patch("sys.stdout", io.StringIO()):
                complete, errors, skipped = run(
                    tasks, real_claude="/fake/claude", output_dir=self.tmp
                )
        self.assertEqual(complete, 2)
        self.assertEqual(errors, 0)
        self.assertEqual(skipped, 0)

    def test_error_causes_dependent_skip(self):
        t1 = Task(id="1", title="T1", prompt="p1")
        t2 = Task(id="2", title="T2", prompt="p2", depends_on=["1"])
        t3 = Task(id="3", title="T3", prompt="p3")  # independent

        def patched_worker(task, *args, **kwargs):
            if task.id == "1":
                self._fake_worker(Status.ERROR)(task, *args, **kwargs)
            else:
                self._fake_worker(Status.COMPLETE)(task, *args, **kwargs)

        with mock.patch("auto_brain.runner._worker", side_effect=patched_worker):
            with mock.patch("sys.stdout", io.StringIO()):
                complete, errors, skipped = run(
                    [t1, t2, t3], real_claude="/fake/claude", output_dir=self.tmp
                )
        self.assertEqual(errors, 1)
        self.assertEqual(skipped, 1)   # t2 skipped because t1 failed
        self.assertEqual(complete, 1)  # t3 unaffected


class ModelDisplayTest(unittest.TestCase):
    def test_alias_unchanged(self):
        self.assertEqual(_model_display("haiku"), "haiku")
        self.assertEqual(_model_display("sonnet"), "sonnet")
        self.assertEqual(_model_display("opus"), "opus")

    def test_full_id_with_version(self):
        self.assertEqual(_model_display("claude-opus-4-7"), "opus 4.7")
        self.assertEqual(_model_display("claude-sonnet-4-6"), "sonnet 4.6")
        self.assertEqual(_model_display("claude-haiku-4-5"), "haiku 4.5")

    def test_full_id_with_date_suffix(self):
        self.assertEqual(_model_display("claude-haiku-4-5-20251001"), "haiku 4.5")

    def test_unknown_model_truncated(self):
        result = _model_display("some-custom-model-xyz")
        self.assertLessEqual(len(result), 15)


class ResolveThinkingTest(unittest.TestCase):
    def test_explicit_thinking_takes_precedence(self):
        t = Task(id="1", title="T", prompt="p", model="haiku", thinking="high")
        self.assertEqual(_resolve_thinking(t), "high")

    def test_derived_from_haiku(self):
        t = Task(id="1", title="T", prompt="p", model="haiku")
        self.assertEqual(_resolve_thinking(t), "low")

    def test_derived_from_sonnet(self):
        t = Task(id="1", title="T", prompt="p", model="sonnet")
        self.assertEqual(_resolve_thinking(t), "med")

    def test_derived_from_opus(self):
        t = Task(id="1", title="T", prompt="p", model="opus")
        self.assertEqual(_resolve_thinking(t), "high")

    def test_custom_map(self):
        t = Task(id="1", title="T", prompt="p", model="haiku")
        self.assertEqual(_resolve_thinking(t, {"haiku": "ext"}), "ext")

    def test_full_model_id_derived(self):
        t = Task(id="1", title="T", prompt="p", model="claude-opus-4-7")
        self.assertEqual(_resolve_thinking(t), "high")

    def test_misspelled_thinking_still_resolves(self):
        t = Task(id="1", title="T", prompt="p", model="haiku", thinking="medium")
        buf = io.StringIO()
        with mock.patch("sys.stderr", buf):
            result = _resolve_thinking(t)
        self.assertEqual(result, "med")
        self.assertIn("normalized", buf.getvalue())


class TimeFieldTest(unittest.TestCase):
    def test_waiting_shows_dashes(self):
        t = Task(id="1", title="T", prompt="p")
        self.assertEqual(_time_field(t), "--")

    def test_running_no_timeout(self):
        t = Task(id="1", title="T", prompt="p", status=Status.RUNNING)
        t.start_time = time.monotonic() - 5.0
        result = _time_field(t)
        self.assertIn("s", result)
        self.assertNotIn("/", result)

    def test_running_with_timeout(self):
        t = Task(id="1", title="T", prompt="p", status=Status.RUNNING, timeout=300)
        t.start_time = time.monotonic() - 10.0
        result = _time_field(t)
        self.assertIn("/", result)
        self.assertIn("300s", result)

    def test_complete_shows_duration(self):
        t = Task(id="1", title="T", prompt="p", status=Status.COMPLETE)
        t.start_time = 100.0
        t.end_time = 104.3
        result = _time_field(t)
        self.assertIn("4.3s", result)

    def test_timeout_error_shows_timeout_label(self):
        t = Task(id="1", title="T", prompt="p", status=Status.ERROR)
        t.start_time = 100.0
        t.end_time = 400.0
        t.error = "timeout after 300s"
        result = _time_field(t)
        self.assertEqual(result, "TIMEOUT")


class NormalizeThinkingTest(unittest.TestCase):
    def test_empty_string_passthrough(self):
        result, warning = _normalize_thinking("")
        self.assertEqual(result, "")
        self.assertIsNone(warning)

    def test_valid_labels_pass_through(self):
        for label in ("low", "med", "high", "ext"):
            result, warning = _normalize_thinking(label)
            self.assertEqual(result, label)
            self.assertIsNone(warning)

    def test_uppercase_valid_label_normalized(self):
        result, warning = _normalize_thinking("HIGH")
        self.assertEqual(result, "high")
        self.assertIsNone(warning)

    def test_mixed_case_valid_label(self):
        result, warning = _normalize_thinking("Med")
        self.assertEqual(result, "med")
        self.assertIsNone(warning)

    def test_alias_medium_to_med(self):
        result, warning = _normalize_thinking("medium")
        self.assertEqual(result, "med")
        self.assertIsNotNone(warning)
        self.assertIn("med", warning)

    def test_alias_extreme_to_ext(self):
        result, warning = _normalize_thinking("extreme")
        self.assertEqual(result, "ext")
        self.assertIsNotNone(warning)

    def test_alias_max_to_ext(self):
        result, warning = _normalize_thinking("max")
        self.assertEqual(result, "ext")
        self.assertIsNotNone(warning)

    def test_alias_case_insensitive(self):
        result, warning = _normalize_thinking("MEDIUM")
        self.assertEqual(result, "med")

    def test_unknown_label_passes_through_with_warning(self):
        result, warning = _normalize_thinking("turbo")
        self.assertEqual(result, "turbo")
        self.assertIsNotNone(warning)
        self.assertIn("valid values", warning)

    def test_unknown_label_warning_lists_valid_values(self):
        _, warning = _normalize_thinking("gibberish")
        for v in ("low", "med", "high", "ext"):
            self.assertIn(v, warning)

    def test_all_aliases_map_to_valid_targets(self):
        for alias in _THINKING_ALIASES:
            result, _ = _normalize_thinking(alias)
            self.assertIn(result, _VALID_THINKING, f"alias '{alias}' maps to invalid '{result}'")


if __name__ == "__main__":
    unittest.main()
