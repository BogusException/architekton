"""
Applies a chain of named transformations to a list of records. Each
transformation is a callable that accepts a record dict and returns a
modified copy. Transformations are registered by name and composed in
the order given.
"""

from typing import Callable


_REGISTRY: dict[str, Callable[[dict], dict]] = {}


def register(name: str):
    """Create a decorator that registers a function as a named transformation.

    Args:
        name: The name to register the transformation under. A later
            registration with the same name replaces the earlier one.

    Returns:
        The decorator to apply to the transformation function.
    """
    def decorator(fn: Callable[[dict], dict]):
        """Store fn in _REGISTRY under the name given to register and return fn.

        Args:
            fn: Callable that takes a record dict and returns a modified record dict.

        Returns:
            The same fn, so the decorated name still refers to the original function.
        """
        _REGISTRY[name] = fn
        return fn
    return decorator


@register("normalize_value")
def normalize_value(record: dict) -> dict:
    """Cast the 'value' field to float; replace non-numeric with 0.0.

    A missing 'value' becomes 0.0. The input record is not modified.

    Args:
        record: The record to transform.

    Returns:
        dict: A copy of the record with 'value' as a float.
    """
    out = dict(record)
    try:
        out["value"] = float(out.get("value", 0))
    except (TypeError, ValueError):
        out["value"] = 0.0
    return out


@register("strip_whitespace")
def strip_whitespace(record: dict) -> dict:
    """Strip leading/trailing whitespace from all string fields.

    Args:
        record: The record to transform.

    Returns:
        dict: A new record with string values stripped. Other values are
        unchanged.
    """
    return {k: v.strip() if isinstance(v, str) else v for k, v in record.items()}


@register("add_flag")
def add_flag(record: dict) -> dict:
    """Add a boolean 'flagged' field: True when value > 100.

    A missing 'value' is treated as 0. The input record is not modified.

    Args:
        record: The record to transform.

    Returns:
        dict: A copy of the record with the 'flagged' field added.

    Raises:
        ValueError: If 'value' is a string that cannot be converted to float.
        TypeError: If 'value' is of a type that float() does not accept, such
            as None.
    """
    out = dict(record)
    out["flagged"] = float(out.get("value", 0)) > 100
    return out


def apply(records: list[dict], steps: list[str]) -> list[dict]:
    """Apply named transformations in order to every record.

    Args:
        records: The records to transform. The list is not modified.
        steps: Names of registered transformations, applied in the order given.

    Returns:
        list[dict]: A new list of transformed records.

    Raises:
        ValueError: If any step name is not registered. No step runs in this
            case. A step such as add_flag can also raise ValueError or
            TypeError for a 'value' that float() rejects.
    """
    unknown = [s for s in steps if s not in _REGISTRY]
    if unknown:
        raise ValueError(f"Unknown transformations: {unknown}")
    result = list(records)
    for step in steps:
        result = [_REGISTRY[step](r) for r in result]
    return result
