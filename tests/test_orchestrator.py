import json
import os
import unittest
from unittest import mock

from auto_brain import orchestrator


class ExtractTasksTest(unittest.TestCase):
    def test_valid_json_array(self):
        data = [{"id": "1", "title": "Do thing", "prompt": "Do it", "model": "haiku", "depends_on": []}]
        result = orchestrator._extract_tasks(json.dumps(data))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "1")
        self.assertEqual(result[0]["title"], "Do thing")

    def test_strips_markdown_fences(self):
        data = [{"id": "1", "prompt": "Do it"}]
        text = f"```json\n{json.dumps(data)}\n```"
        result = orchestrator._extract_tasks(text)
        self.assertEqual(result[0]["id"], "1")

    def test_extracts_json_from_prose(self):
        data = [{"id": "1", "prompt": "Do it"}]
        text = f"Here is the plan:\n{json.dumps(data)}\nEnd."
        result = orchestrator._extract_tasks(text)
        self.assertEqual(result[0]["id"], "1")

    def test_defaults_missing_optional_fields(self):
        data = [{"id": "1", "prompt": "Do it"}]
        result = orchestrator._extract_tasks(json.dumps(data))
        self.assertEqual(result[0]["title"], "1")
        self.assertEqual(result[0]["model"], "haiku")
        self.assertEqual(result[0]["depends_on"], [])

    def test_custom_default_model(self):
        data = [{"id": "1", "prompt": "Do it"}]
        result = orchestrator._extract_tasks(json.dumps(data), default_model="sonnet")
        self.assertEqual(result[0]["model"], "sonnet")

    def test_raises_on_missing_id(self):
        data = [{"prompt": "Do it"}]
        with self.assertRaises(ValueError):
            orchestrator._extract_tasks(json.dumps(data))

    def test_raises_on_missing_prompt(self):
        data = [{"id": "1", "title": "T"}]
        with self.assertRaises(ValueError):
            orchestrator._extract_tasks(json.dumps(data))

    def test_raises_when_no_json_array(self):
        with self.assertRaises((ValueError, json.JSONDecodeError)):
            orchestrator._extract_tasks("Here is my plan: nothing structured.")

    def test_title_truncated_to_60(self):
        data = [{"id": "1", "title": "x" * 100, "prompt": "Do it"}]
        result = orchestrator._extract_tasks(json.dumps(data))
        self.assertLessEqual(len(result[0]["title"]), 60)

    def test_depends_on_converted_to_strings(self):
        data = [{"id": "2", "prompt": "Do it", "depends_on": [1]}]
        result = orchestrator._extract_tasks(json.dumps(data))
        self.assertEqual(result[0]["depends_on"], ["1"])

    def test_multiple_tasks(self):
        data = [
            {"id": "1", "prompt": "First"},
            {"id": "2", "prompt": "Second", "depends_on": ["1"]},
        ]
        result = orchestrator._extract_tasks(json.dumps(data))
        self.assertEqual(len(result), 2)
        self.assertEqual(result[1]["depends_on"], ["1"])

    def test_thinking_field_passed_through(self):
        data = [{"id": "1", "prompt": "Do it", "thinking": "high"}]
        result = orchestrator._extract_tasks(json.dumps(data))
        self.assertEqual(result[0]["thinking"], "high")

    def test_thinking_field_defaults_to_empty(self):
        data = [{"id": "1", "prompt": "Do it"}]
        result = orchestrator._extract_tasks(json.dumps(data))
        self.assertEqual(result[0]["thinking"], "")


class DecomposeTest(unittest.TestCase):
    def _mock_run(self, tasks_data, returncode=0, stderr=""):
        return mock.patch(
            "subprocess.run",
            return_value=mock.Mock(
                returncode=returncode,
                stdout=json.dumps(tasks_data),
                stderr=stderr,
            ),
        )

    def test_calls_real_claude_with_correct_model(self):
        tasks = [{"id": "1", "prompt": "Do it"}]
        with self._mock_run(tasks) as mock_run:
            orchestrator.decompose("Build a thing", model="opus", real_claude="/usr/bin/claude")
        args = mock_run.call_args[0][0]
        self.assertEqual(args[0], "/usr/bin/claude")
        self.assertIn("--model=opus", args)
        self.assertIn("--print", args)

    def test_sets_smartmodel_disable_in_env(self):
        tasks = [{"id": "1", "prompt": "Do it"}]
        with self._mock_run(tasks) as mock_run:
            orchestrator.decompose("Build", real_claude="/usr/bin/claude")
        env = mock_run.call_args[1]["env"]
        self.assertEqual(env.get("SMARTMODEL_DISABLE"), "1")

    def test_preamble_prepended_to_prompt(self):
        tasks = [{"id": "1", "prompt": "Do it"}]
        with self._mock_run(tasks) as mock_run:
            orchestrator.decompose("Build", real_claude="/usr/bin/claude", preamble="PREFIX\n")
        prompt_arg = mock_run.call_args[0][0][-1]
        self.assertTrue(prompt_arg.startswith("PREFIX\n"))

    def test_job_description_in_prompt(self):
        tasks = [{"id": "1", "prompt": "Do it"}]
        with self._mock_run(tasks) as mock_run:
            orchestrator.decompose("My specific job", real_claude="/usr/bin/claude")
        prompt_arg = mock_run.call_args[0][0][-1]
        self.assertIn("My specific job", prompt_arg)

    def test_raises_on_nonzero_exit(self):
        with self._mock_run([], returncode=1, stderr="something went wrong"):
            with self.assertRaises(RuntimeError) as ctx:
                orchestrator.decompose("Build", real_claude="/usr/bin/claude")
        self.assertIn("something went wrong", str(ctx.exception))

    def test_returns_validated_tasks(self):
        tasks = [{"id": "1", "prompt": "Do it"}, {"id": "2", "prompt": "Then this", "depends_on": ["1"]}]
        with self._mock_run(tasks):
            result = orchestrator.decompose("Build", real_claude="/usr/bin/claude")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[1]["depends_on"], ["1"])


if __name__ == "__main__":
    unittest.main()
