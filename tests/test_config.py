import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from architekton import config

REPO = Path(__file__).resolve().parent.parent


class ConfigTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.claude_dir = root / "claude"
        self.project = root / "project"
        (self.claude_dir / "architekton").mkdir(parents=True)
        (self.project / ".claude").mkdir(parents=True)
        env = mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(self.claude_dir)})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("ARCHITEKTON_DISABLE", None)

    def write(self, path, data):
        path.write_text(json.dumps(data), encoding="utf-8")

    def global_config(self, data):
        self.write(self.claude_dir / "architekton" / "config.json", data)

    def project_config(self, data):
        self.write(self.project / ".claude" / "architekton.json", data)

    def project_settings(self, data):
        self.write(self.project / ".claude" / "settings.json", data)

    def global_settings(self, data):
        self.write(self.claude_dir / "settings.json", data)

    def test_no_files_gives_defaults(self):
        self.assertEqual(config.load(self.project), config.DEFAULTS)
        self.assertEqual(config.resolve_model(self.project), ("sonnet", "built-in default"))

    def test_project_overrides_global(self):
        self.global_config({"enabled": False, "thresholds": {"heavy": 0.9}})
        self.project_config({"enabled": True})
        merged = config.load(self.project)
        self.assertTrue(merged["enabled"])
        self.assertEqual(merged["thresholds"], {"light": 0.30, "heavy": 0.9})

    def test_load_does_not_mutate_defaults(self):
        self.global_config({"thresholds": {"heavy": 0.9}})
        config.load(self.project)
        self.assertEqual(config.DEFAULTS["thresholds"]["heavy"], 0.65)

    def test_model_priority_order(self):
        self.global_settings({"model": "haiku"})
        self.assertEqual(config.resolve_model(self.project)[0], "haiku")
        self.global_config({"default_model": "sonnet"})
        self.assertEqual(config.resolve_model(self.project)[0], "sonnet")
        self.project_config({"default_model": "opus"})
        self.assertEqual(config.resolve_model(self.project), ("opus", "project .claude/architekton.json"))
        self.project_settings({"model": "haiku"})
        self.assertEqual(config.resolve_model(self.project), ("haiku", "project .claude/settings.json"))

    def test_disable_env_wins(self):
        self.assertTrue(config.is_enabled(config.load(self.project)))
        with mock.patch.dict(os.environ, {"ARCHITEKTON_DISABLE": "1"}):
            self.assertFalse(config.is_enabled(config.load(self.project)))

    def test_invalid_json_raises(self):
        (self.claude_dir / "architekton" / "config.json").write_text("{nope", encoding="utf-8")
        with self.assertRaises(config.ConfigError):
            config.load(self.project)

    def test_invalid_mode_raises(self):
        self.global_config({"mode": "chaos"})
        with self.assertRaises(config.ConfigError):
            config.load(self.project)

    def test_set_global_enabled_keeps_other_keys(self):
        self.global_config({"default_model": "opus"})
        config.set_global_enabled(False)
        saved = json.loads((self.claude_dir / "architekton" / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(saved, {"default_model": "opus", "enabled": False})

    def test_global_template_matches_defaults(self):
        template = json.loads((REPO / "config" / ".defaults" / "global.json").read_text(encoding="utf-8"))
        self.assertEqual(template, config.DEFAULTS)


class ConfigValidationTest(unittest.TestCase):
    def _validate(self, job_cfg):
        buf = io.StringIO()
        with mock.patch("sys.stderr", buf):
            config._validate_job_config(job_cfg)
        return buf.getvalue()

    def test_valid_config_no_warnings(self):
        warnings = self._validate({
            "worker_thinking": "high",
            "thinking_map": {"haiku": "low", "sonnet": "med", "opus": "high"},
            "orchestrator_model": "opus",
            "worker_model": "haiku",
        })
        self.assertEqual(warnings, "")

    def test_unknown_thinking_in_map_warns(self):
        warnings = self._validate({"thinking_map": {"opus": "turbo"}})
        self.assertIn("turbo", warnings)
        self.assertIn("thinking_map", warnings)

    def test_unknown_worker_thinking_warns(self):
        warnings = self._validate({"worker_thinking": "ultra_high_plus"})
        self.assertIn("ultra_high_plus", warnings)

    def test_known_alias_in_thinking_map_no_unknown_warning(self):
        # "medium" is a known alias; should NOT trigger the "unknown" error message
        warnings = self._validate({"thinking_map": {"opus": "medium"}})
        self.assertNotIn("unknown thinking level", warnings)

    def test_unrecognized_model_warns(self):
        warnings = self._validate({"worker_model": "gpt-4o"})
        self.assertIn("gpt-4o", warnings)
        self.assertIn("worker_model", warnings)

    def test_full_model_id_no_warning(self):
        warnings = self._validate({
            "orchestrator_model": "claude-opus-4-7",
            "worker_model": "claude-haiku-4-5-20251001",
        })
        self.assertEqual(warnings, "")

    def test_valid_alias_no_warning(self):
        warnings = self._validate({
            "orchestrator_model": "opus",
            "worker_model": "sonnet",
        })
        self.assertEqual(warnings, "")

    def test_empty_job_cfg_no_warnings(self):
        warnings = self._validate({})
        self.assertEqual(warnings, "")

    def test_unknown_worker_thinking_alias_warns_about_normalization(self):
        # "medium" is a known alias: should warn about normalization, not crash
        warnings = self._validate({"worker_thinking": "medium"})
        self.assertIn("medium", warnings)


if __name__ == "__main__":
    unittest.main()
