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
    """Create a decorator that registers a validation rule by name.

    Args:
        name: The name to register the rule under. A later registration with
            the same name replaces the earlier one.

    Returns:
        The decorator to apply to the rule function.
    """
    def decorator(fn: RuleFunc):
        """Register fn in the rule registry under the name passed to rule().

        Args:
            fn: The rule function to register. It takes a record dict and
                returns None on pass or a failure message string.

        Returns:
            The same function, unchanged.
        """
        _RULES[name] = fn
        return fn
    return decorator


@rule("has_id")
def has_id(record: dict) -> str | None:
    """Check that the record has a non-empty 'id' field.

    Args:
        record: The record to check.

    Returns:
        A failure message if 'id' is missing or falsy, otherwise None.
    """
    if not record.get("id"):
        return "missing or empty 'id'"
    return None


@rule("value_non_negative")
def value_non_negative(record: dict) -> str | None:
    """Check that the record's 'value' field is numeric and not negative.

    A missing 'value' is treated as 0 and passes.

    Args:
        record: The record to check.

    Returns:
        A failure message if 'value' is negative or not numeric, otherwise
        None.
    """
    try:
        if float(record.get("value", 0)) < 0:
            return f"'value' is negative: {record['value']}"
    except (TypeError, ValueError):
        return f"'value' is not numeric: {record.get('value')!r}"
    return None


@rule("name_not_empty")
def name_not_empty(record: dict) -> str | None:
    """Check that the record's 'name' field is not blank after stripping.

    A missing 'name' is treated as an empty string and fails.

    Args:
        record: The record to check.

    Returns:
        A failure message if 'name' is missing or blank, otherwise None.
    """
    if not str(record.get("name", "")).strip():
        return "missing or empty 'name'"
    return None


@dataclass
class RecordResult:
    """Validation outcome for a single record.

    Attributes:
        record_id: The record's 'id' as a string, or "(no id)" if absent.
        passed: True when no rule reported a failure.
        failures: Failure messages, each prefixed with the rule name.
    """

    record_id: str
    passed: bool
    failures: list[str] = field(default_factory=list)


@dataclass
class ValidationReport:
    """Aggregate validation outcome for a batch of records.

    Attributes:
        total: Number of records validated.
        passed: Number of records with no failures.
        failed: Number of records with at least one failure.
        results: One RecordResult per validated record, in input order.
    """

    total: int
    passed: int
    failed: int
    results: list[RecordResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Report whether every record passed.

        Returns:
            True if no record failed, otherwise False.
        """
        return self.failed == 0


def validate(records: list[dict], rules: list[str] | None = None) -> ValidationReport:
    """Run named rules (or all rules) against every record.

    Args:
        records: The records to validate.
        rules: Names of registered rules to run. If None or empty, all
            registered rules run.

    Returns:
        ValidationReport: The totals and one RecordResult per record, in input
        order. Each failure message is prefixed with the rule name.

    Raises:
        ValueError: If any rule name is not registered. No record is checked
            in this case.
    """
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
