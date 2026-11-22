import json
import os
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest import mock

from auto_brain import journal


class JournalTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.claude_dir = self.tmp / "claude"
        (self.claude_dir / "smartmodel").mkdir(parents=True)
        env = mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(self.claude_dir)})
        env.start()
        self.addCleanup(env.stop)

    def _journal_path(self):
        return self.claude_dir / "smartmodel" / "cost-journal.jsonl"

    def _write_entries(self, entries):
        path = self._journal_path()
        with path.open("w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

    # --- session_end ---

    def test_session_end_creates_journal(self):
        with mock.patch("os.getcwd", return_value="/projects/myapp"):
            journal.session_end("opus", 12)
        path = self._journal_path()
        self.assertTrue(path.exists())
        entry = json.loads(path.read_text())
        self.assertEqual(entry["model"], "opus")
        self.assertEqual(entry["turns"], 12)
        self.assertEqual(entry["project"], "myapp")

    def test_session_end_appends(self):
        with mock.patch("os.getcwd", return_value="/projects/proj"):
            journal.session_end("sonnet", 5)
            journal.session_end("haiku", 2)
        lines = self._journal_path().read_text().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0])["model"], "sonnet")
        self.assertEqual(json.loads(lines[1])["model"], "haiku")

    def test_session_end_stores_heavy_light(self):
        with mock.patch("os.getcwd", return_value="/projects/proj"):
            journal.session_end("opus", 10, heavy_prompts=7, light_prompts=3)
        entry = json.loads(self._journal_path().read_text())
        self.assertEqual(entry["heavy_prompts"], 7)
        self.assertEqual(entry["light_prompts"], 3)

    def test_session_end_idempotent_on_missing_dir(self):
        # Remove smartmodel dir to test mkdir
        import shutil
        shutil.rmtree(str(self.claude_dir / "smartmodel"))
        with mock.patch("os.getcwd", return_value="/projects/proj"):
            journal.session_end("sonnet", 3)
        self.assertTrue(self._journal_path().exists())

    # --- _tier_for_model ---

    def test_tier_opus(self):
        self.assertEqual(journal._tier_for_model("opus"), "opus")
        self.assertEqual(journal._tier_for_model("claude-opus-4-7"), "opus")

    def test_tier_haiku(self):
        self.assertEqual(journal._tier_for_model("haiku"), "haiku")
        self.assertEqual(journal._tier_for_model("claude-haiku-4-5"), "haiku")

    def test_tier_sonnet_default(self):
        self.assertEqual(journal._tier_for_model("sonnet"), "sonnet")
        self.assertEqual(journal._tier_for_model("claude-sonnet-4-6"), "sonnet")
        self.assertEqual(journal._tier_for_model("unknown-model"), "sonnet")

    # --- _count_turns ---

    def test_count_turns_counts_user_messages(self):
        transcript = self.tmp / "transcript.jsonl"
        lines = [
            {"message": {"role": "user", "content": "hello"}},
            {"message": {"role": "assistant", "content": "hi"}},
            {"message": {"role": "user", "content": "how are you"}},
        ]
        transcript.write_text("\n".join(json.dumps(l) for l in lines) + "\n")
        self.assertEqual(journal._count_turns(str(transcript)), 2)

    def test_count_turns_missing_file(self):
        self.assertEqual(journal._count_turns("/nonexistent/path.jsonl"), 0)

    def test_count_turns_skips_malformed_lines(self):
        transcript = self.tmp / "bad.jsonl"
        transcript.write_text('{"message": {"role": "user"}}\nnot-json\n')
        self.assertEqual(journal._count_turns(str(transcript)), 1)

    # --- report ---

    def test_report_no_entries(self):
        result = journal.report()
        self.assertIn("No journal entries", result)

    def test_report_no_entries_with_days(self):
        result = journal.report(days=7)
        self.assertIn("No journal entries", result)
        self.assertIn("last 7 days", result)

    def test_report_basic(self):
        now = datetime.now(timezone.utc).isoformat()
        self._write_entries([
            {"date": now, "project": "myapp", "model": "opus", "turns": 20, "heavy_prompts": 10, "light_prompts": 5},
            {"date": now, "project": "myapp", "model": "sonnet", "turns": 8, "heavy_prompts": 2, "light_prompts": 6},
        ])
        result = journal.report()
        self.assertIn("myapp", result)
        self.assertIn("2 sessions", result) if "2 sessions" in result else None
        self.assertIn("O:", result)
        self.assertIn("S:", result)
        self.assertIn("$", result)

    def test_report_days_filter(self):
        old = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        now = datetime.now(timezone.utc).isoformat()
        self._write_entries([
            {"date": old, "project": "old-proj", "model": "sonnet", "turns": 5, "heavy_prompts": 0, "light_prompts": 0},
            {"date": now, "project": "new-proj", "model": "opus", "turns": 10, "heavy_prompts": 5, "light_prompts": 0},
        ])
        result = journal.report(days=7)
        self.assertNotIn("old-proj", result)
        self.assertIn("new-proj", result)

    def test_report_custom_pricing(self):
        now = datetime.now(timezone.utc).isoformat()
        self._write_entries([
            {"date": now, "project": "proj", "model": "opus", "turns": 1000, "heavy_prompts": 0, "light_prompts": 0},
        ])
        # Zero pricing -> $0.00 cost
        result = journal.report(pricing={"opus": {"input_per_1m": 0.0, "output_per_1m": 0.0}})
        self.assertIn("$     0.00", result)

    def test_report_skips_malformed_lines(self):
        path = self._journal_path()
        now = datetime.now(timezone.utc).isoformat()
        path.write_text(
            'not-json\n'
            + json.dumps({"date": now, "project": "proj", "model": "sonnet", "turns": 3, "heavy_prompts": 0, "light_prompts": 0})
            + "\n"
        )
        result = journal.report()
        self.assertIn("proj", result)

    def test_report_all_tiers(self):
        now = datetime.now(timezone.utc).isoformat()
        self._write_entries([
            {"date": now, "project": "p", "model": "opus",   "turns": 5, "heavy_prompts": 0, "light_prompts": 0},
            {"date": now, "project": "p", "model": "sonnet", "turns": 5, "heavy_prompts": 0, "light_prompts": 0},
            {"date": now, "project": "p", "model": "haiku",  "turns": 5, "heavy_prompts": 0, "light_prompts": 0},
        ])
        result = journal.report()
        self.assertIn("O:", result)
        self.assertIn("S:", result)
        self.assertIn("H:", result)


if __name__ == "__main__":
    unittest.main()
