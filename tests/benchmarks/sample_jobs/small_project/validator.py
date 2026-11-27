"""
Validates processed records against a set of rules. Each rule is a
function that returns None on pass or a string describing the failure.
Returns a ValidationReport with per-record results and an overall pass/fail.
"""

from dataclasses import dataclass, field
from typing import Callable


RuleFunc = Callable[[dict], str | None]

_RULES: dict[str, RuleFunc] = {}


def rule(name: str):
    """Decorator: register a validation rule by name."""
    def decorator(fn: RuleFunc):
        _RULES[name] = fn
        return fn
    return decorator


@rule("has_id")
def has_id(record: dict) -> str | None:
    if not record.get("id"):
        return "missing or empty 'id'"
    return None


@rule("value_non_negative")
def value_non_negative(record: dict) -> str | None:
    try:
        if float(record.get("value", 0)) < 0:
            return f"'value' is negative: {record['value']}"
    except (TypeError, ValueError):
        return f"'value' is not numeric: {record.get('value')!r}"
    return None


@rule("name_not_empty")
def name_not_empty(record: dict) -> str | None:
    if not str(record.get("name", "")).strip():
        return "missing or empty 'name'"
    return None


@dataclass
class RecordResult:
    record_id: str
    passed: bool
    failures: list[str] = field(default_factory=list)


@dataclass
class ValidationReport:
    total: int
    passed: int
    failed: int
    results: list[RecordResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.failed == 0


def validate(records: list[dict], rules: list[str] | None = None) -> ValidationReport:
    """Run named rules (or all rules) against every record."""
    active_rules = rules or list(_RULES)
    unknown = [r for r in active_rules if r not in _RULES]
    if unknown:
        raise ValueError(f"Unknown rules: {unknown}")

    results = []
    for record in records:
        failures = []
        for rule_name in active_rules:
            msg = _RULES[rule_name](record)
            if msg:
                failures.append(f"{rule_name}: {msg}")
        results.append(RecordResult(
            record_id=str(record.get("id", "(no id)")),
            passed=not failures,
            failures=failures,
        ))

    passed = sum(1 for r in results if r.passed)
    return ValidationReport(
        total=len(results),
        passed=passed,
        failed=len(results) - passed,
        results=results,
    )
