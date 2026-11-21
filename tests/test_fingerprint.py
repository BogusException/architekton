import tempfile
import unittest
from pathlib import Path

from auto_brain import fingerprint


class BashHeavyTest(unittest.TestCase):
    def _mkproj(self, content):
        d = tempfile.mkdtemp()
        Path(d, ".mkproj").write_text(content, encoding="utf-8")
        return d

    def test_bash_heavy_mkproj_returns_opus(self):
        content = "#!/bin/bash\nfunction setup() {\nif [ -d /tmp ]; then\nfor f in *.txt; do\ncase $1 in\n"
        result = fingerprint.detect(self._mkproj(content))
        self.assertEqual(result["tier"], "opus")
        self.assertIn("bash", result["reason"])

    def test_mkproj_without_enough_bash_patterns_does_not_bias(self):
        # Only one pattern -- below threshold of 3
        result = fingerprint.detect(self._mkproj("#!/bin/bash\n# just a comment\n"))
        self.assertIsNone(result["tier"])

    def test_mkproj_absent_skips_bash_check(self):
        with tempfile.TemporaryDirectory() as d:
            result = fingerprint.detect(d)
        self.assertIsNone(result["tier"])


class DataScienceTest(unittest.TestCase):
    def _req(self, lines):
        d = tempfile.mkdtemp()
        Path(d, "requirements.txt").write_text("\n".join(lines), encoding="utf-8")
        return d

    def test_numpy_and_pandas_returns_sonnet(self):
        result = fingerprint.detect(self._req(["numpy>=1.24", "pandas==2.0.0"]))
        self.assertEqual(result["tier"], "sonnet")
        self.assertIn("numpy", result["reason"])

    def test_torch_returns_sonnet(self):
        result = fingerprint.detect(self._req(["torch", "torchvision"]))
        self.assertEqual(result["tier"], "sonnet")

    def test_no_data_science_packages_no_bias(self):
        result = fingerprint.detect(self._req(["requests", "flask", "click"]))
        self.assertIsNone(result["tier"])

    def test_comment_lines_are_ignored(self):
        result = fingerprint.detect(self._req(["# numpy is great", "requests"]))
        self.assertIsNone(result["tier"])

    def test_package_with_extras_is_parsed(self):
        result = fingerprint.detect(self._req(["tensorflow[and-cuda]>=2.0"]))
        self.assertEqual(result["tier"], "sonnet")

    def test_data_science_wins_over_docs_only(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "requirements.txt").write_text("numpy\n", encoding="utf-8")
            Path(d, "README.md").write_text("# docs\n", encoding="utf-8")
            result = fingerprint.detect(d)
        self.assertEqual(result["tier"], "sonnet")


class DocsOnlyTest(unittest.TestCase):
    def test_md_files_no_code_returns_haiku(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "README.md").write_text("# docs\n", encoding="utf-8")
            Path(d, "guide.md").write_text("# guide\n", encoding="utf-8")
            result = fingerprint.detect(d)
        self.assertEqual(result["tier"], "haiku")
        self.assertIn("docs", result["reason"])

    def test_project_with_py_files_is_not_docs_only(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "README.md").write_text("# docs\n", encoding="utf-8")
            Path(d, "main.py").write_text("print('hello')\n", encoding="utf-8")
            result = fingerprint.detect(d)
        self.assertNotEqual(result["tier"], "haiku")

    def test_rst_docs_counts_as_docs_only(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "index.rst").write_text("Index\n=====\n", encoding="utf-8")
            result = fingerprint.detect(d)
        self.assertEqual(result["tier"], "haiku")

    def test_no_docs_and_no_code_has_no_fingerprint(self):
        with tempfile.TemporaryDirectory() as d:
            result = fingerprint.detect(d)
        self.assertIsNone(result["tier"])


class NoMatchTest(unittest.TestCase):
    def test_typical_code_project_has_no_fingerprint(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d, "src")
            src.mkdir()
            (src / "main.py").write_text("def run(): pass\n", encoding="utf-8")
            Path(d, "README.md").write_text("# project\n", encoding="utf-8")
            result = fingerprint.detect(d)
        self.assertIsNone(result["tier"])
        self.assertEqual(result["reason"], "no fingerprint matched")


if __name__ == "__main__":
    unittest.main()
