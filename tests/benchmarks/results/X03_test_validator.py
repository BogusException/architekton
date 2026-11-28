"""Unit tests for the original small_project validator module."""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "sample_jobs" / "small_project"),
)

import validator  # noqa: E402
from validator import (  # noqa: E402
    RecordResult,
    ValidationReport,
    has_id,
    name_not_empty,
    validate,
    value_non_negative,
)

VALID = {"id": "a1", "value": 5, "name": "Widget"}


# ---------- rule registry ----------

def test_rules_registered():
    assert set(validator._RULES) == {"has_id", "value_non_negative", "name_not_empty"}
    assert validator._RULES["has_id"] is has_id


def test_rule_decorator_registers_and_returns_function():
    def fn(record):
        return None

    try:
        assert validator.rule("tmp_rule")(fn) is fn
        assert validator._RULES["tmp_rule"] is fn
    finally:
        validator._RULES.pop("tmp_rule", None)


# ---------- has_id ----------

@pytest.mark.parametrize("record, expected", [
    ({"id": "a1"}, None),
    ({"id": 7}, None),
    ({"id": "0"}, None),
    ({}, "missing or empty 'id'"),
    ({"id": ""}, "missing or empty 'id'"),
    ({"id": None}, "missing or empty 'id'"),
    ({"id": 0}, "missing or empty 'id'"),
])
def test_has_id(record, expected):
    assert has_id(record) == expected


# ---------- value_non_negative ----------

@pytest.mark.parametrize("record", [
    {"value": 5},
    {"value": 0},          # boundary: zero passes
    {"value": -0.0},
    {"value": 0.0001},
    {"value": "3.5"},      # numeric string
    {"value": " 2 "},      # float() tolerates whitespace
    {"value": True},
    {},                    # missing defaults to 0
])
def test_value_passes(record):
    assert value_non_negative(record) is None


@pytest.mark.parametrize("record, expected", [
    ({"value": -1}, "'value' is negative: -1"),      # boundary: just below zero
    ({"value": -0.0001}, "'value' is negative: -0.0001"),
    ({"value": "-2"}, "'value' is negative: -2"),
    ({"value": "abc"}, "'value' is not numeric: 'abc'"),
    ({"value": ""}, "'value' is not numeric: ''"),
    ({"value": None}, "'value' is not numeric: None"),
    ({"value": [1]}, "'value' is not numeric: [1]"),
])
def test_value_fails(record, expected):
    assert value_non_negative(record) == expected


def test_value_nan_is_accepted_today():
    # Documents current behavior: NaN is not < 0, so it passes.
    assert value_non_negative({"value": math.nan}) is None


# ---------- name_not_empty ----------

@pytest.mark.parametrize("record", [
    {"name": "x"},        # boundary: one char
    {"name": " x "},
    {"name": 0},          # str(0) == "0"
])
def test_name_passes(record):
    assert name_not_empty(record) is None


@pytest.mark.parametrize("record", [
    {},
    {"name": ""},         # boundary: zero length
    {"name": " "},
    {"name": "\t\n "},
])
def test_name_fails(record):
    assert name_not_empty(record) == "missing or empty 'name'"


@pytest.mark.xfail(
    reason="Bug: name_not_empty uses str(None) == 'None', so name=None passes as non-empty",
    strict=True,
)
def test_name_none_should_fail():
    assert name_not_empty({"name": None}) == "missing or empty 'name'"


# ---------- validate: happy path and structure ----------

def test_validate_fully_valid_record():
    report = validate([VALID])
    assert isinstance(report, ValidationReport)
    assert (report.total, report.passed, report.failed) == (1, 1, 0)
    assert report.ok is True
    assert report.results == [RecordResult(record_id="a1", passed=True, failures=[])]


def test_validate_empty_record_list():
    report = validate([])
    assert (report.total, report.passed, report.failed) == (0, 0, 0)
    assert report.results == []
    assert report.ok is True


# ---------- validate: each rule failing alone ----------

@pytest.mark.parametrize("record, expected_failures", [
    ({"id": "", "value": 1, "name": "n"},
     ["has_id: missing or empty 'id'"]),
    ({"id": "a", "value": -5, "name": "n"},
     ["value_non_negative: 'value' is negative: -5"]),
    ({"id": "a", "value": "x", "name": "n"},
     ["value_non_negative: 'value' is not numeric: 'x'"]),
    ({"id": "a", "value": 1, "name": "  "},
     ["name_not_empty: missing or empty 'name'"]),
])
def test_validate_single_rule_failure(record, expected_failures):
    report = validate([record])
    assert report.results[0].failures == expected_failures
    assert report.results[0].passed is False
    assert (report.passed, report.failed) == (0, 1)
    assert report.ok is False


# ---------- validate: several failures ----------

def test_validate_multiple_failures_in_registration_order():
    report = validate([{"id": "", "value": -1, "name": ""}])
    assert report.results[0].failures == [
        "has_id: missing or empty 'id'",
        "value_non_negative: 'value' is negative: -1",
        "name_not_empty: missing or empty 'name'",
    ]


def test_validate_mixed_records_counts():
    records = [
        VALID,
        {"id": "b", "value": -1, "name": "n"},
        {"id": "c", "value": 0, "name": "n"},
        {},
    ]
    report = validate(records)
    assert (report.total, report.passed, report.failed) == (4, 2, 2)
    assert [r.passed for r in report.results] == [True, False, True, False]
    assert report.ok is False


# ---------- validate: missing fields and None ----------

def test_validate_empty_dict_record():
    report = validate([{}])
    result = report.results[0]
    assert result.record_id == "(no id)"
    # missing value defaults to 0 and passes
    assert result.failures == [
        "has_id: missing or empty 'id'",
        "name_not_empty: missing or empty 'name'",
    ]


@pytest.mark.parametrize("record, expected_id", [
    ({"id": "a1"}, "a1"),
    ({"id": 42}, "42"),
    ({"id": None}, "None"),
    ({"id": ""}, ""),
    ({"name": "n"}, "(no id)"),
])
def test_validate_record_id_text(record, expected_id):
    assert validate([record], rules=["has_id"]).results[0].record_id == expected_id


def test_validate_all_none_values():
    report = validate([{"id": None, "value": None, "name": None}])
    failures = report.results[0].failures
    assert "has_id: missing or empty 'id'" in failures
    assert "value_non_negative: 'value' is not numeric: None" in failures


def test_validate_none_record_raises():
    with pytest.raises(AttributeError):
        validate([None])


# ---------- validate: rule selection ----------

def test_validate_rule_subset():
    record = {"id": "", "value": -1, "name": ""}
    report = validate([record], rules=["value_non_negative"])
    assert report.results[0].failures == ["value_non_negative: 'value' is negative: -1"]


def test_validate_rules_run_in_given_order():
    record = {"id": "", "value": -1, "name": ""}
    report = validate([record], rules=["name_not_empty", "has_id"])
    assert [f.split(":")[0] for f in report.results[0].failures] == [
        "name_not_empty", "has_id",
    ]


def test_validate_empty_rules_list_runs_all_rules():
    report = validate([{}], rules=[])
    assert len(report.results[0].failures) == 2


@pytest.mark.parametrize("rules, unknown", [
    (["nope"], ["nope"]),
    (["has_id", "nope", "bad"], ["nope", "bad"]),
])
def test_validate_unknown_rules_raise(rules, unknown):
    with pytest.raises(ValueError, match="Unknown rules") as exc:
        validate([VALID], rules=rules)
    assert str(unknown) in str(exc.value)


def test_validate_unknown_rule_raises_even_for_empty_records():
    with pytest.raises(ValueError):
        validate([], rules=["nope"])


def test_validate_custom_rule_via_registry():
    @validator.rule("always_fail")
    def always_fail(record):
        return "boom"

    try:
        report = validate([VALID], rules=["always_fail"])
        assert report.results[0].failures == ["always_fail: boom"]
    finally:
        validator._RULES.pop("always_fail", None)


# ---------- ValidationReport.ok ----------

@pytest.mark.parametrize("failed, expected", [(0, True), (1, False), (5, False)])
def test_report_ok(failed, expected):
    assert ValidationReport(total=5, passed=5 - failed, failed=failed).ok is expected
