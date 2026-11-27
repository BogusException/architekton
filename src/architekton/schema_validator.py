"""Validate a config dict against config/schema.json (stdlib only).

Returns a list of human-readable error strings. Empty list = valid.
Does not raise; callers decide whether to warn or block.
"""

import json
import re
from pathlib import Path

_SCHEMA_PATH = Path(__file__).parent.parent.parent / "config" / "schema.json"
_schema_cache = None


def _load_schema():
    global _schema_cache
    if _schema_cache is None:
        _schema_cache = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return _schema_cache


def _resolve_ref(ref, schema):
    """Resolve a $ref like '#/$defs/thinking_level' against the root schema."""
    if not ref.startswith("#/"):
        return {}
    parts = ref[2:].split("/")
    node = schema
    for part in parts:
        node = node.get(part, {})
    return node


def _check_node(value, node, schema_root, path, errors):
    """Recursively validate value against node, appending to errors."""
    # Resolve $ref
    if "$ref" in node:
        node = _resolve_ref(node["$ref"], schema_root)

    # anyOf: valid if any branch passes
    if "anyOf" in node:
        branch_errors = []
        for branch in node["anyOf"]:
            sub = []
            _check_node(value, branch, schema_root, path, sub)
            if not sub:
                return
            branch_errors.extend(sub)
        errors.append(f"{path}: no valid type match ({'; '.join(branch_errors[:2])})")
        return

    expected_type = node.get("type")
    if expected_type and value is not None:
        type_ok = {
            "boolean": lambda v: isinstance(v, bool),
            "string":  lambda v: isinstance(v, str),
            "number":  lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
            "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
            "object":  lambda v: isinstance(v, dict),
        }.get(expected_type, lambda v: True)(value)
        if not type_ok:
            errors.append(f"{path}: expected {expected_type}, got {type(value).__name__}")
            return

    if "enum" in node and value not in node["enum"]:
        errors.append(f"{path}: must be one of {node['enum']!r}, got {value!r}")
        return

    if expected_type == "number" or expected_type == "integer":
        if "minimum" in node and value < node["minimum"]:
            errors.append(f"{path}: {value} is below minimum {node['minimum']}")
        if "maximum" in node and value > node["maximum"]:
            errors.append(f"{path}: {value} exceeds maximum {node['maximum']}")

    if expected_type == "string" and "pattern" in node and value:
        if not re.fullmatch(node["pattern"], value):
            errors.append(f"{path}: {value!r} does not match pattern {node['pattern']}")

    if expected_type == "object" and isinstance(value, dict):
        props = node.get("properties", {})
        additional_ok = node.get("additionalProperties", True)
        if additional_ok is False:
            for k in value:
                if k not in props:
                    errors.append(f"{path}.{k}: unknown key")
        for k, sub_node in props.items():
            if k in value:
                _check_node(value[k], sub_node, schema_root, f"{path}.{k}", errors)
        # additionalProperties as a schema (thinking_map uses this)
        if isinstance(additional_ok, dict) and additional_ok:
            for k, v in value.items():
                if k not in props:
                    _check_node(v, additional_ok, schema_root, f"{path}.{k}", errors)


def validate(config: dict) -> list[str]:
    """Return a list of error strings for config. Empty = valid."""
    schema = _load_schema()
    errors: list[str] = []
    props = schema.get("properties", {})
    if schema.get("additionalProperties") is False:
        for k in config:
            if k not in props:
                errors.append(f"{k}: unknown top-level key")
    for key, node in props.items():
        if key in config:
            _check_node(config[key], node, schema, key, errors)
    return errors
