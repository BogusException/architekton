"""
Applies a chain of named transformations to a list of records. Each
transformation is a callable that accepts a record dict and returns a
modified copy. Transformations are registered by name and composed in
the order given.
"""

from typing import Callable


_REGISTRY: dict[str, Callable[[dict], dict]] = {}


def register(name: str):
    """Decorator: register a function as a named transformation."""
    def decorator(fn: Callable[[dict], dict]):
        _REGISTRY[name] = fn
        return fn
    return decorator


@register("normalize_value")
def normalize_value(record: dict) -> dict:
    """Cast the 'value' field to float; replace non-numeric with 0.0."""
    out = dict(record)
    try:
        out["value"] = float(out.get("value", 0))
    except (TypeError, ValueError):
        out["value"] = 0.0
    return out


@register("strip_whitespace")
def strip_whitespace(record: dict) -> dict:
    """Strip leading/trailing whitespace from all string fields."""
    return {k: v.strip() if isinstance(v, str) else v for k, v in record.items()}


@register("add_flag")
def add_flag(record: dict) -> dict:
    """Add a boolean 'flagged' field: True when value > 100."""
    out = dict(record)
    out["flagged"] = float(out.get("value", 0)) > 100
    return out


def apply(records: list[dict], steps: list[str]) -> list[dict]:
    """Apply named transformations in order to every record."""
    unknown = [s for s in steps if s not in _REGISTRY]
    if unknown:
        raise ValueError(f"Unknown transformations: {unknown}")
    result = list(records)
    for step in steps:
        result = [_REGISTRY[step](r) for r in result]
    return result
