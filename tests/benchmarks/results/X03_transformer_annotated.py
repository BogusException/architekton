"""
Applies a chain of named transformations to a list of records. Each
transformation is a callable that accepts a record dict and returns a
modified copy. Transformations are registered by name and composed in
the order given.
"""

from typing import Callable


_REGISTRY: dict[str, Callable[[dict], dict]] = {}


def register(name: str) -> Callable[[Callable[[dict], dict]], Callable[[dict], dict]]:
    """Decorator: register a function as a named transformation.

    Args:
        name: Registry key under which the decorated function is stored.
            Registering the same name twice replaces the earlier function.

    Returns:
        A decorator that stores the function in the registry and returns it
        unchanged.
    """
    def decorator(fn: Callable[[dict], dict]) -> Callable[[dict], dict]:
        """Store fn in the registry under the enclosing name.

        Args:
            fn: Callable[[dict], dict] to register.

        Returns:
            The same function, unchanged.
        """
        _REGISTRY[name] = fn
        return fn
    return decorator


@register("normalize_value")
def normalize_value(record: dict) -> dict:
    """Cast the 'value' field to float; replace non-numeric with 0.0.

    A missing 'value' key is treated as 0. The input record is not mutated.

    Args:
        record: Input record. May lack a 'value' key.

    Returns:
        A shallow copy of the record with 'value' as a float.
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

    Non-string values are passed through unchanged. The input record is not
    mutated.

    Args:
        record: Input record.

    Returns:
        A new dict with every string value stripped.
    """
    return {k: v.strip() if isinstance(v, str) else v for k, v in record.items()}


@register("add_flag")
def add_flag(record: dict) -> dict:
    """Add a boolean 'flagged' field: True when value > 100.

    A missing 'value' key is treated as 0. The input record is not mutated.

    Args:
        record: Input record. 'value' must be convertible by float().

    Returns:
        A shallow copy of the record with a 'flagged' bool added.

    Raises:
        ValueError: If 'value' is a string that cannot be parsed as a float.
        TypeError: If 'value' is of a type float() does not accept (for
            example None or a list).
    """
    out = dict(record)
    out["flagged"] = float(out.get("value", 0)) > 100
    return out


def apply(records: list[dict], steps: list[str]) -> list[dict]:
    """Apply named transformations in order to every record.

    The steps are validated before any record is processed. The input list
    is not mutated, and the registered transformations return new dicts.

    Args:
        records: Records to transform.
        steps: Names of registered transformations, applied in order.

    Returns:
        A new list of transformed records. With no steps, a shallow copy of
        the input list (the record dicts themselves are shared).

    Raises:
        ValueError: If any name in steps is not registered.
        Exception: Anything raised by a transformation, such as the errors
            documented on add_flag, propagates unchanged.
    """
    unknown = [s for s in steps if s not in _REGISTRY]
    if unknown:
        raise ValueError(f"Unknown transformations: {unknown}")
    result = list(records)
    for step in steps:
        result = [_REGISTRY[step](r) for r in result]
    return result
