"""Tests for small_project/validator.py."""

import dataclasses
import sys
from pathlib import Path

SMALL_PROJECT_DIR = (
    Path(__file__).resolve().parent.parent / "sample_jobs" / "small_project"
)
sys.path.insert(0, str(SMALL_PROJECT_DIR))

import pytest  # noqa: E402

import validator  # noqa: E402
from validator import (  # noqa: E402
    RecordResult,
    ValidationReport,
    has_id,
    name_not_empty,
    rule,
    validate,
    value_non_negative,
)

BUILTIN_NAMES = ["has_id", "value_non_negative", "name_not_empty"]


@pytest.fixture
def isolated_rules(monkeypatch):
    """Replace the module rule registry with a copy that tests may mutate."""
    registry = dict(validator._RULES)
    monkeypatch.setattr(validator, "_RULES", registry)
    return registry


# ---------------------------------------------------------------- registry


def test_builtin_rules_registered_in_order():
    """The three built-in rules are registered under their names in definition order."""
    assert list(validator._RULES) == BUILTIN_NAMES


def test_builtin_registry_maps_to_functions():
    """Each registered name maps to the matching module-level function."""
    assert validator._RULES["has_id"] is has_id
    assert validator._RULES["value_non_negative"] is value_non_negative
    assert validator._RULES["name_not_empty"] is name_not_empty


def test_rule_decorator_registers_and_returns_function(isolated_rules):
    """The rule decorator stores the function under the name and returns it unchanged."""
    def custom(record):
        return None

    returned = rule("custom")(custom)
    assert returned is custom
    assert isolated_rules["custom"] is custom


def test_rule_decorator_overwrites_existing_name(isolated_rules):
    """Registering a rule under an existing name replaces the earlier rule."""
    def replacement(record):
        return "always"

    rule("has_id")(replacement)
    assert isolated_rules["has_id"] is replacement


# ------------------------------------------------------------------ has_id


@pytest.mark.parametrize("record_id", [1, "a", "0", 99999, True, [1], ("x",)])
def test_has_id_passes_for_truthy_ids(record_id):
    """has_id returns None when the id value is truthy."""
    assert has_id({"id": record_id}) is None


@pytest.mark.parametrize("record_id", [None, "", 0, 0.0, False, [], {}])
def test_has_id_fails_for_falsy_ids(record_id):
    """has_id reports a failure when the id is present but falsy."""
    assert has_id({"id": record_id}) == "missing or empty 'id'"


def test_has_id_fails_when_key_missing():
    """has_id reports a failure when the record has no id key."""
    assert has_id({}) == "missing or empty 'id'"


@pytest.mark.parametrize("bad", [None, 5, "text", [("id", 1)]])
def test_has_id_non_dict_raises_attribute_error(bad):
    """has_id raises AttributeError when the record has no .get method."""
    with pytest.raises(AttributeError):
        has_id(bad)


def test_has_id_whitespace_id_is_truthy():
    """A whitespace-only id is truthy, so has_id does not strip it."""
    assert has_id({"id": "   "}) is None


# ------------------------------------------------------ value_non_negative


@pytest.mark.parametrize(
    "value",
    [0, 0.0, -0.0, 1, 3.14, "0", "5", " 7 ", "1e3", True, False, float("inf"),
     float("nan")],
)
def test_value_non_negative_passes(value):
    """value_non_negative returns None for zero, positive, numeric strings, bools, inf and nan."""
    assert value_non_negative({"value": value}) is None


def test_value_non_negative_missing_value_defaults_to_zero():
    """A record without 'value' is treated as 0 and passes."""
    assert value_non_negative({}) is None


@pytest.mark.parametrize(
    "value, expected",
    [
        (-1, "'value' is negative: -1"),
        (-0.001, "'value' is negative: -0.001"),
        (-5.5, "'value' is negative: -5.5"),
        ("-3", "'value' is negative: -3"),
        (float("-inf"), "'value' is negative: -inf"),
    ],
)
def test_value_non_negative_negative_message_uses_raw_value(value, expected):
    """A negative value fails with a message that formats the original value with str()."""
    assert value_non_negative({"value": value}) == expected


def test_value_non_negative_threshold_boundary():
    """Exactly 0 passes while the smallest step below 0 fails."""
    assert value_non_negative({"value": 0}) is None
    assert value_non_negative({"value": -1e-12}) is not None


@pytest.mark.parametrize(
    "value, expected",
    [
        (None, "'value' is not numeric: None"),
        ("abc", "'value' is not numeric: 'abc'"),
        ("", "'value' is not numeric: ''"),
        ([], "'value' is not numeric: []"),
        ({}, "'value' is not numeric: {}"),
        ((1, 2), "'value' is not numeric: (1, 2)"),
        (object, "'value' is not numeric: " + repr(object)),
    ],
)
def test_value_non_negative_non_numeric_uses_repr(value, expected):
    """Values float() rejects (TypeError or ValueError) yield a 'not numeric' message using repr()."""
    assert value_non_negative({"value": value}) == expected


def test_value_non_negative_complex_is_not_numeric():
    """A complex number raises TypeError in float() and is reported as not numeric."""
    assert value_non_negative({"value": 1 + 2j}) == "'value' is not numeric: (1+2j)"


def test_value_non_negative_non_dict_raises_attribute_error():
    """A record without .get raises AttributeError, which the rule does not catch."""
    with pytest.raises(AttributeError):
        value_non_negative(None)


# -------------------------------------------------------- name_not_empty


@pytest.mark.parametrize("name", ["a", "Bob", " x ", "0", 0, 123, None, False, [], 0.0])
def test_name_not_empty_passes_when_str_is_nonblank(name):
    """name_not_empty passes whenever str(name).strip() is non-empty (None becomes 'None')."""
    assert name_not_empty({"name": name}) is None


@pytest.mark.parametrize("name", ["", " ", "   ", "\t", "\n", " \t\n "])
def test_name_not_empty_fails_for_blank_strings(name):
    """name_not_empty fails for empty and whitespace-only strings."""
    assert name_not_empty({"name": name}) == "missing or empty 'name'"


def test_name_not_empty_fails_when_key_missing():
    """A missing name key defaults to '' and fails."""
    assert name_not_empty({}) == "missing or empty 'name'"


def test_name_not_empty_non_dict_raises_attribute_error():
    """A record without .get raises AttributeError."""
    with pytest.raises(AttributeError):
        name_not_empty(42)


def test_name_not_empty_propagates_str_failure():
    """An exception raised by the name object's __str__ is not caught by the rule."""
    class Bad:
        def __str__(self):
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        name_not_empty({"name": Bad()})


# ------------------------------------------------------------- dataclasses


def test_record_result_defaults():
    """RecordResult.failures defaults to an empty list."""
    r = RecordResult(record_id="x", passed=True)
    assert r.record_id == "x"
    assert r.passed is True
    assert r.failures == []


def test_record_result_default_lists_not_shared():
    """Each RecordResult gets its own failures list."""
    a = RecordResult("a", True)
    b = RecordResult("b", True)
    a.failures.append("x")
    assert b.failures == []


def test_record_result_equality_and_fields():
    """RecordResult is a dataclass with value equality and the three declared fields."""
    assert dataclasses.is_dataclass(RecordResult)
    assert [f.name for f in dataclasses.fields(RecordResult)] == [
        "record_id", "passed", "failures",
    ]
    assert RecordResult("a", False, ["f"]) == RecordResult("a", False, ["f"])
    assert RecordResult("a", False, ["f"]) != RecordResult("a", True, ["f"])


def test_validation_report_defaults():
    """ValidationReport.results defaults to an empty list."""
    rep = ValidationReport(total=0, passed=0, failed=0)
    assert rep.results == []


def test_validation_report_default_lists_not_shared():
    """Each ValidationReport gets its own results list."""
    a = ValidationReport(0, 0, 0)
    b = ValidationReport(0, 0, 0)
    a.results.append(RecordResult("x", True))
    assert b.results == []


def test_validation_report_requires_counts():
    """total, passed and failed are required constructor arguments."""
    with pytest.raises(TypeError):
        ValidationReport()
    with pytest.raises(TypeError):
        ValidationReport(total=1, passed=1)


@pytest.mark.parametrize(
    "failed, expected", [(0, True), (1, False), (5, False), (-1, False)]
)
def test_validation_report_ok_property(failed, expected):
    """ok is True only when failed == 0, regardless of other fields."""
    assert ValidationReport(total=5, passed=5, failed=failed).ok is expected


def test_validation_report_ok_ignores_results_content():
    """ok depends on the failed counter, not on the results list."""
    rep = ValidationReport(1, 0, 0, [RecordResult("a", False, ["x"])])
    assert rep.ok is True


def test_validation_report_ok_is_read_only_property():
    """ok is a property without a setter, so assigning to it raises AttributeError."""
    rep = ValidationReport(0, 0, 0)
    with pytest.raises(AttributeError):
        rep.ok = False


# ---------------------------------------------------------------- validate


GOOD = {"id": 1, "value": 10, "name": "alpha"}


def test_validate_empty_records():
    """An empty record list gives an empty, ok report."""
    rep = validate([])
    assert (rep.total, rep.passed, rep.failed) == (0, 0, 0)
    assert rep.results == []
    assert rep.ok is True


def test_validate_all_rules_pass():
    """Records that satisfy every rule produce passed results with no failures."""
    rep = validate([GOOD, {"id": "b", "value": "0", "name": "x"}])
    assert (rep.total, rep.passed, rep.failed) == (2, 2, 0)
    assert rep.ok is True
    assert all(r.passed and r.failures == [] for r in rep.results)


def test_validate_returns_validation_report_of_record_results():
    """validate returns a ValidationReport holding RecordResult instances."""
    rep = validate([GOOD])
    assert isinstance(rep, ValidationReport)
    assert isinstance(rep.results[0], RecordResult)


def test_validate_single_failure_message_format():
    """A failure string is '<rule name>: <rule message>'."""
    rep = validate([{"id": 1, "value": -2, "name": "n"}])
    assert rep.results[0].failures == ["value_non_negative: 'value' is negative: -2"]
    assert rep.results[0].passed is False
    assert (rep.total, rep.passed, rep.failed) == (1, 0, 1)
    assert rep.ok is False


def test_validate_multiple_failures_in_rule_order():
    """A record failing all rules lists failures in registry order."""
    rep = validate([{"id": "", "value": "zzz", "name": " "}])
    assert rep.results[0].failures == [
        "has_id: missing or empty 'id'",
        "value_non_negative: 'value' is not numeric: 'zzz'",
        "name_not_empty: missing or empty 'name'",
    ]


def test_validate_mixed_records_counts_and_order():
    """Counts add up and results keep the input order for mixed pass/fail records."""
    records = [
        GOOD,
        {"id": 2, "value": -1, "name": "b"},
        {"id": 3, "value": 1, "name": "c"},
        {"id": 4, "value": 1, "name": ""},
    ]
    rep = validate(records)
    assert (rep.total, rep.passed, rep.failed) == (4, 2, 2)
    assert [r.record_id for r in rep.results] == ["1", "2", "3", "4"]
    assert [r.passed for r in rep.results] == [True, False, True, False]
    assert rep.ok is False


def test_validate_missing_id_uses_placeholder_and_fails_has_id():
    """A record with no id key gets record_id '(no id)' and fails has_id."""
    rep = validate([{"value": 1, "name": "n"}])
    assert rep.results[0].record_id == "(no id)"
    assert rep.results[0].failures == ["has_id: missing or empty 'id'"]


def test_validate_empty_record_fails_every_rule_except_value():
    """An empty dict fails has_id and name_not_empty; value defaults to 0 and passes."""
    rep = validate([{}])
    assert rep.results[0].record_id == "(no id)"
    assert rep.results[0].failures == [
        "has_id: missing or empty 'id'",
        "name_not_empty: missing or empty 'name'",
    ]


@pytest.mark.parametrize(
    "record_id, expected",
    [
        (1, "1"),
        (0, "0"),
        (1.5, "1.5"),
        ("abc", "abc"),
        ("", ""),
        (None, "None"),
        (False, "False"),
        (True, "True"),
        ([1, 2], "[1, 2]"),
    ],
)
def test_validate_record_id_is_converted_with_str(record_id, expected):
    """record_id is str(record['id']) when the key exists, even for None, 0 or ''."""
    rep = validate([{"id": record_id, "value": 1, "name": "n"}], rules=["value_non_negative"])
    assert rep.results[0].record_id == expected
    assert isinstance(rep.results[0].record_id, str)


def test_validate_falsy_id_keeps_str_id_and_fails_has_id():
    """id=0 is stringified to '0' but still fails has_id because 0 is falsy."""
    rep = validate([{"id": 0, "value": 1, "name": "n"}])
    assert rep.results[0].record_id == "0"
    assert rep.results[0].failures == ["has_id: missing or empty 'id'"]


def test_validate_rule_subset_runs_only_named_rules():
    """Passing rules limits checking to those rules."""
    rep = validate([{"id": "", "value": -1, "name": ""}], rules=["name_not_empty"])
    assert rep.results[0].failures == ["name_not_empty: missing or empty 'name'"]


def test_validate_rule_subset_uses_given_order():
    """Failures follow the order of the rules argument, not registry order."""
    rep = validate(
        [{"id": "", "value": -1, "name": ""}],
        rules=["name_not_empty", "has_id"],
    )
    assert [f.split(":")[0] for f in rep.results[0].failures] == [
        "name_not_empty", "has_id",
    ]


def test_validate_duplicate_rule_names_run_twice():
    """Listing a rule twice runs it twice and records the failure twice."""
    rep = validate([{"id": ""}], rules=["has_id", "has_id"])
    assert rep.results[0].failures == ["has_id: missing or empty 'id'"] * 2


def test_validate_empty_rules_list_means_all_rules():
    """An empty rules list is falsy, so validate falls back to every registered rule."""
    rep = validate([{}], rules=[])
    assert len(rep.results[0].failures) == 2


def test_validate_none_rules_means_all_rules():
    """rules=None runs every registered rule."""
    rep = validate([{}], rules=None)
    assert len(rep.results[0].failures) == 2


def test_validate_records_can_be_any_iterable():
    """validate only iterates records, so a generator works."""
    rep = validate(r for r in [GOOD, GOOD])
    assert rep.total == 2


def test_validate_does_not_mutate_records():
    """validate leaves the input records unchanged."""
    record = {"id": 1, "value": "5", "name": " n "}
    snapshot = dict(record)
    validate([record])
    assert record == snapshot


# ------------------------------------------------------ validate: errors


def test_validate_unknown_rule_raises_value_error():
    """An unregistered rule name raises ValueError listing the unknown names."""
    with pytest.raises(ValueError) as exc:
        validate([GOOD], rules=["nope", "has_id", "also_nope"])
    assert str(exc.value) == "Unknown rules: ['nope', 'also_nope']"


def test_validate_unknown_rule_raises_before_processing_records():
    """The rule name check happens first, so it raises even for an empty record list."""
    with pytest.raises(ValueError, match="Unknown rules"):
        validate([], rules=["nope"])


def test_validate_unknown_rule_raises_even_if_records_invalid():
    """The ValueError wins over record errors because names are checked up front."""
    with pytest.raises(ValueError):
        validate([None], rules=["nope"])


def test_validate_string_rules_is_iterated_per_character():
    """A bare string for rules is iterated by character, so 'has_id' is reported as unknown letters."""
    with pytest.raises(ValueError) as exc:
        validate([GOOD], rules="has_id")
    assert str(exc.value) == "Unknown rules: ['h', 'a', 's', '_', 'i', 'd']"


def test_validate_rule_names_are_case_sensitive():
    """Rule lookup is case-sensitive."""
    with pytest.raises(ValueError, match="HAS_ID"):
        validate([GOOD], rules=["HAS_ID"])


@pytest.mark.parametrize("bad_rules", [[None], [1], [("has_id",)]])
def test_validate_non_string_hashable_rule_is_unknown(bad_rules):
    """Hashable non-string entries are not in the registry and raise ValueError."""
    with pytest.raises(ValueError, match="Unknown rules"):
        validate([GOOD], rules=bad_rules)


def test_validate_unhashable_rule_entry_raises_type_error():
    """An unhashable entry (a list) makes the registry membership test raise TypeError."""
    with pytest.raises(TypeError):
        validate([GOOD], rules=[["has_id"]])


def test_validate_int_rules_raises_type_error():
    """A non-iterable truthy rules value raises TypeError when iterated."""
    with pytest.raises(TypeError):
        validate([GOOD], rules=5)


def test_validate_records_none_raises_type_error():
    """records=None is not iterable and raises TypeError."""
    with pytest.raises(TypeError):
        validate(None)


def test_validate_records_int_raises_type_error():
    """records=int is not iterable and raises TypeError."""
    with pytest.raises(TypeError):
        validate(5)


@pytest.mark.parametrize("bad", [None, 5, "text", ["a"]])
def test_validate_non_dict_record_raises_attribute_error(bad):
    """A record without .get raises AttributeError from the first rule that reads it."""
    with pytest.raises(AttributeError):
        validate([bad])


def test_validate_non_dict_record_error_not_wrapped_after_good_records():
    """The AttributeError propagates; no partial report is returned."""
    with pytest.raises(AttributeError):
        validate([GOOD, None])


def test_validate_string_records_iterates_characters_and_raises():
    """A bare string for records yields str items, which lack .get, giving AttributeError."""
    with pytest.raises(AttributeError):
        validate("abc")


def test_validate_dict_records_iterates_keys_and_raises():
    """A dict passed as records iterates its keys (strings), giving AttributeError."""
    with pytest.raises(AttributeError):
        validate({"id": 1})


# ------------------------------------------ validate: custom/broken rules


def test_validate_custom_registered_rule_is_used(isolated_rules):
    """A rule added via the decorator runs in validate and is named in failures."""
    @rule("short_name")
    def short_name(record):
        return "too long" if len(record.get("name", "")) > 3 else None

    rep = validate([{"id": 1, "name": "abcdef"}], rules=["short_name"])
    assert rep.results[0].failures == ["short_name: too long"]


def test_validate_custom_rule_included_in_default_run(isolated_rules):
    """With rules=None, a newly registered rule runs after the built-ins."""
    rule("always_fail")(lambda record: "nope")
    rep = validate([GOOD])
    assert rep.results[0].failures == ["always_fail: nope"]


@pytest.mark.parametrize("returned", ["", None, 0, False, []])
def test_validate_falsy_rule_result_counts_as_pass(isolated_rules, returned):
    """Any falsy rule return value, including an empty string, is treated as a pass."""
    rule("falsy")(lambda record: returned)
    rep = validate([GOOD], rules=["falsy"])
    assert rep.results[0].passed is True
    assert rep.results[0].failures == []


def test_validate_truthy_non_string_result_is_formatted(isolated_rules):
    """A truthy non-string return value is formatted into the failure message."""
    rule("num")(lambda record: 42)
    rep = validate([GOOD], rules=["num"])
    assert rep.results[0].failures == ["num: 42"]


def test_validate_exception_inside_rule_propagates(isolated_rules):
    """An exception raised by a rule is not caught by validate."""
    def exploding(record):
        raise RuntimeError("rule blew up")

    rule("exploding")(exploding)
    with pytest.raises(RuntimeError, match="rule blew up"):
        validate([GOOD], rules=["exploding"])


def test_validate_keyerror_inside_rule_propagates(isolated_rules):
    """A rule that indexes a missing field raises KeyError out of validate."""
    rule("needs_x")(lambda record: None if record["x"] else "falsy x")
    with pytest.raises(KeyError):
        validate([{"id": 1}], rules=["needs_x"])
    assert validate([{"id": 1, "x": 0}], rules=["needs_x"]).results[0].failures == [
        "needs_x: falsy x"
    ]


def test_validate_exception_stops_processing_remaining_records(isolated_rules):
    """After a rule raises, later records are not processed."""
    seen = []

    def tracker(record):
        seen.append(record["id"])
        if record["id"] == 2:
            raise RuntimeError("stop")
        return None

    rule("tracker")(tracker)
    with pytest.raises(RuntimeError):
        validate([{"id": 1}, {"id": 2}, {"id": 3}], rules=["tracker"])
    assert seen == [1, 2]


@pytest.mark.parametrize("not_callable", [42, "text", None, [], {}])
def test_validate_non_callable_rule_raises_type_error(isolated_rules, not_callable):
    """A non-callable object in the registry raises TypeError when validate calls it."""
    isolated_rules["broken"] = not_callable
    with pytest.raises(TypeError):
        validate([GOOD], rules=["broken"])


def test_validate_non_callable_rule_not_called_for_empty_records(isolated_rules):
    """With no records the rule is never invoked, so a non-callable rule goes unnoticed."""
    isolated_rules["broken"] = 42
    rep = validate([], rules=["broken"])
    assert rep.total == 0


def test_rule_decorator_accepts_non_callable_without_error(isolated_rules):
    """The decorator does not check callability; it registers and returns the object."""
    obj = 123
    assert rule("n")(obj) == 123
    assert isolated_rules["n"] == 123


def test_validate_rule_returning_object_with_bad_format_raises(isolated_rules):
    """An f-string over a result whose __format__ raises propagates the exception."""
    class Bad:
        def __bool__(self):
            return True

        def __format__(self, spec):
            raise ValueError("fmt")

    rule("badfmt")(lambda record: Bad())
    with pytest.raises(ValueError, match="fmt"):
        validate([GOOD], rules=["badfmt"])
