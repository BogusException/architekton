"""Load and merge auto-brain config from global and project scope."""

import json
import os
from pathlib import Path

DEFAULTS = {
    "enabled": True,
    "mode": "auto",
    "default_model": "sonnet",
    "models": {"haiku": "haiku", "sonnet": "sonnet", "opus": "opus"},
    "thresholds": {"light": 0.30, "heavy": 0.65},
    "pricing": {
        "opus":   {"input_per_1m": 15.00, "output_per_1m": 75.00},
        "sonnet": {"input_per_1m":  3.00, "output_per_1m": 15.00},
        "haiku":  {"input_per_1m":  0.80, "output_per_1m":  4.00},
    },
    "job": {
        "orchestrator_model":    "opus",
        "worker_model":          "haiku",
        "max_parallel":          4,
        "worker_timeout":        300,
        "worker_max_turns":      20,
        "orchestrator_preamble": "",
    },
}
VALID_MODES = ("auto", "advisory")


class ConfigError(Exception):
    pass


def get_claude_dir():
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def get_global_config_path():
    return get_claude_dir() / "smartmodel" / "config.json"


def get_project_dir():
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())


def get_project_config_path(project_dir=None):
    return (project_dir or get_project_dir()) / ".claude" / "smartmodel.json"


def read_json(path):
    """Return the parsed JSON object at path, or {} when the file is missing."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ConfigError(f"{path}: invalid JSON ({error})") from error
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: expected a JSON object")
    return data


def load(project_dir=None):
    """Merge defaults, global config, then project config (later wins)."""
    merged = {key: dict(value) if isinstance(value, dict) else value for key, value in DEFAULTS.items()}
    for path in (get_global_config_path(), get_project_config_path(project_dir)):
        for key, value in read_json(path).items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key].update(value)
            else:
                merged[key] = value
    if merged["mode"] not in VALID_MODES:
        raise ConfigError(f"mode must be one of {VALID_MODES}, got {merged['mode']!r}")
    return merged


def is_enabled(config):
    return bool(config["enabled"]) and os.environ.get("SMARTMODEL_DISABLE") != "1"


def resolve_model(project_dir=None):
    """Return (model, source) for the session default.

    Walks the priority order from docs/architecture.md section 3, minus the
    explicit --model flag, which the wrapper handles before calling us.
    """
    project_dir = project_dir or get_project_dir()
    candidates = (
        ("project .claude/settings.json", read_json(project_dir / ".claude" / "settings.json").get("model")),
        ("project .claude/smartmodel.json", read_json(get_project_config_path(project_dir)).get("default_model")),
        ("global smartmodel config", read_json(get_global_config_path()).get("default_model")),
        ("global ~/.claude/settings.json", read_json(get_claude_dir() / "settings.json").get("model")),
    )
    for source, model in candidates:
        if isinstance(model, str) and model:
            return model, source
    return DEFAULTS["default_model"], "built-in default"


def set_global_enabled(should_enable):
    """Write enabled into the global config, keeping any other keys."""
    path = get_global_config_path()
    data = read_json(path)
    data["enabled"] = should_enable
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
