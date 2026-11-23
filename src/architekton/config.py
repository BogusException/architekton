"""Load and merge architekton config from global and project scope."""

import json
import os
from pathlib import Path

from architekton.schema_validator import validate as _schema_validate

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
        "thinking_map":          {"haiku": "low", "sonnet": "med", "opus": "high"},
        "worker_thinking":       "",
    },
    "tui": {
        "color":           True,
        "status_waiting":  "dim",
        "status_running":  "cyan",
        "status_complete": "green",
        "status_error":    "red",
        "status_skipped":  "yellow",
        "model_haiku":     "green",
        "model_sonnet":    "cyan",
        "model_opus":      "red",
        "model_other":     "",
        "separator":       "dim",
        "row_bg":          "",
        "show_orchestrator": True,
    },
}
VALID_MODES = ("auto", "advisory")

_VALID_THINKING    = frozenset({"low", "med", "high", "ext"})
_THINKING_ALIASES  = frozenset({"medium", "normal", "moderate", "minimal", "minimum",
                                 "extreme", "max", "maximum", "extended", "ultra"})
_KNOWN_MODEL_FAMILIES = frozenset({"haiku", "sonnet", "opus"})


def _warn(msg):
    import sys
    print(f"[architekton config] {msg}", file=sys.stderr)


def _looks_like_model(s):
    """Return True if s looks like a valid Claude model alias or full ID."""
    low = s.lower()
    return low in _KNOWN_MODEL_FAMILIES or low.startswith("claude-")


def _validate_job_config(job_cfg):
    """Emit warnings for suspicious values in the job config section. Never raises."""
    wthinking = job_cfg.get("worker_thinking", "")
    if wthinking:
        low = wthinking.lower()
        if low not in _VALID_THINKING and low not in _THINKING_ALIASES:
            _warn(
                f"job.worker_thinking: unknown thinking level '{wthinking}'; "
                f"valid: low, med, high, ext. Common aliases: medium=med, extreme/max=ext."
            )
        elif low in _THINKING_ALIASES:
            _ALIAS_MAP = {
                "medium": "med", "normal": "med", "moderate": "med",
                "minimal": "low", "minimum": "low",
                "extreme": "ext", "max": "ext", "maximum": "ext", "extended": "ext", "ultra": "ext",
            }
            normalized = _ALIAS_MAP.get(low, low)
            _warn(
                f"job.worker_thinking: '{wthinking}' is a known alias -- "
                f"it will be normalized to '{normalized}' at display time. "
                f"Update config to use the canonical label."
            )

    for tier, level in job_cfg.get("thinking_map", {}).items():
        if isinstance(level, str) and level:
            low = level.lower()
            if low not in _VALID_THINKING and low not in _THINKING_ALIASES:
                _warn(
                    f"job.thinking_map['{tier}']: unknown thinking level '{level}'; "
                    f"valid: low, med, high, ext"
                )

    for key in ("orchestrator_model", "worker_model"):
        val = job_cfg.get(key, "")
        if isinstance(val, str) and val and not _looks_like_model(val):
            _warn(
                f"job.{key}: '{val}' is not a recognized Claude model alias "
                f"(haiku, sonnet, opus) or full model ID (e.g. claude-opus-4-7). "
                f"Workers will fail if the model is unavailable."
            )


class ConfigError(Exception):
    pass


def get_claude_dir():
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def get_global_config_path():
    return get_claude_dir() / "architekton" / "config.json"


def get_project_dir():
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())


def get_project_config_path(project_dir=None):
    return (project_dir or get_project_dir()) / ".claude" / "architekton.json"


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
    if isinstance(merged.get("job"), dict):
        _validate_job_config(merged["job"])
    for err in _schema_validate(merged):
        _warn(f"config validation: {err}")
    return merged


def is_enabled(config):
    return bool(config["enabled"]) and os.environ.get("ARCHITEKTON_DISABLE") != "1"


def resolve_model(project_dir=None):
    """Return (model, source) for the session default.

    Walks the priority order from docs/architecture.md section 3, minus the
    explicit --model flag, which the wrapper handles before calling us.
    """
    project_dir = project_dir or get_project_dir()
    candidates = (
        ("project .claude/settings.json", read_json(project_dir / ".claude" / "settings.json").get("model")),
        ("project .claude/architekton.json", read_json(get_project_config_path(project_dir)).get("default_model")),
        ("global architekton config", read_json(get_global_config_path()).get("default_model")),
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


_BACKUP_KEEP = 10


def _rotate_backups(path):
    """Keep at most _BACKUP_KEEP timestamped backups of path."""
    import time
    backup_dir = path.parent / "config.backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d%H%M%S")
    backup = backup_dir / f"config.{stamp}.json"
    if path.exists():
        import shutil
        shutil.copy2(path, backup)
    # Prune oldest beyond _BACKUP_KEEP
    backups = sorted(backup_dir.glob("config.*.json"))
    for old in backups[:-_BACKUP_KEEP]:
        old.unlink(missing_ok=True)
    return backup


def save_global_config(data: dict) -> None:
    """Validate data, rotate a backup, then write to the global config path.

    Raises ConfigError if schema validation fails so the caller (TUI) can
    show the errors without writing a broken config.
    """
    errors = _schema_validate(data)
    if errors:
        raise ConfigError("config validation failed:\n  " + "\n  ".join(errors))
    path = get_global_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    _rotate_backups(path)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def list_config_backups() -> list:
    """Return backup paths sorted oldest to newest."""
    backup_dir = get_global_config_path().parent / "config.backups"
    if not backup_dir.exists():
        return []
    return sorted(backup_dir.glob("config.*.json"))


def restore_config(backup_path=None) -> Path:
    """Restore global config from backup_path, or from the factory default.

    Returns the path that was restored from.
    """
    import shutil
    target = get_global_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    if backup_path is None:
        factory = Path(__file__).parent.parent.parent / "config" / ".defaults" / "global.json"
        source = factory
    else:
        source = Path(backup_path)
    if not source.exists():
        raise ConfigError(f"restore source not found: {source}")
    _rotate_backups(target)
    shutil.copy2(source, target)
    return source
