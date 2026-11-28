"""Tests for small_project/transformer.py."""

import copy
import math
import sys
from pathlib import Path

SMALL_PROJECT = (
    Path(__file__).resolve().parent.parent / "sample_jobs" / "small_project"
)
sys.path.insert(0, str(SMALL_PROJECT))

import pytest  # noqa: E402

import transformer  # noqa: E402
from transformer import (  # noqa: E402
    add_flag,
    apply,
    normalize_value,
    register,
    strip_whitespace,
)


# --------------------------------------------------------------------------
# Registry and register()
# --------------------------------------------------------------------------


def test_builtin_steps_are_registered():
    """The three built-in steps are present in the registry under their names."""
    assert transformer._REGISTRY["normalize_value"] is normalize_value
    assert transformer._REGISTRY["strip_whitespace"] is strip_whitespace
    assert transformer._REGISTRY["add_flag"] is add_flag


def test_register_returns_function_and_adds_to_registry(monkeypatch):
    """register() stores the function under the name and returns it unchanged."""
    monkeypatch.setattr(transformer, "_REGISTRY", dict(transformer._REGISTRY))

    @register("custom")
    def custom(record):
        return record

    assert transformer._REGISTRY["custom"] is custom
    assert custom({"a": 1}) == {"a": 1}


def test_register_same_name_overwrites(monkeypatch):
    """Registering a second function under an existing name replaces the first."""
    monkeypatch.setattr(transformer, "_REGISTRY", dict(transformer._REGISTRY))

    @register("dup")
    def first(record):
        return {"who": "first"}

    @register("dup")
    def second(record):
        return {"who": "second"}

    assert apply([{}], ["dup"]) == [{"who": "second"}]


# --------------------------------------------------------------------------
# normalize_value
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        (5, 5.0),
        (2.5, 2.5),
        ("42", 42.0),
        ("3.14", 3.14),
        (" 7 ", 7.0),
        ("1e3", 1000.0),
        (True, 1.0),
        (0, 0.0),
        (-3, -3.0),
        ("-3.5", -3.5),
        ("0", 0.0),
    ],
)
def test_normalize_value_casts_numeric_values(raw, expected):
    """normalize_value converts numeric and numeric-string values to float."""
    out = normalize_value({"value": raw})
    assert out["value"] == expected
    assert isinstance(out["value"], float)


@pytest.mark.parametrize("raw", ["abc", "", "   ", None, [1], {"a": 1}, (1, 2), object()])
def test_normalize_value_replaces_non_numeric_with_zero(raw):
    """Values float() rejects with TypeError or ValueError become 0.0."""
    assert normalize_value({"value": raw})["value"] == 0.0


def test_normalize_value_missing_field_defaults_to_zero():
    """A record without 'value' gets value 0.0 added."""
    assert normalize_value({"id": 1}) == {"id": 1, "value": 0.0}


def test_normalize_value_empty_record():
    """An empty dict gains a 'value' of 0.0."""
    assert normalize_value({}) == {"value": 0.0}


def test_normalize_value_preserves_other_fields():
    """Fields other than 'value' pass through untouched."""
    out = normalize_value({"id": 9, "name": " x ", "value": "2"})
    assert out == {"id": 9, "name": " x ", "value": 2.0}


def test_normalize_value_nan_and_inf_strings_are_accepted():
    """float() accepts 'nan' and 'inf', so they are kept rather than zeroed."""
    assert math.isnan(normalize_value({"value": "nan"})["value"])
    assert normalize_value({"value": "inf"})["value"] == math.inf


def test_normalize_value_returns_new_dict_and_does_not_mutate_input():
    """The input record is left unchanged and a different dict is returned."""
    rec = {"value": "5"}
    out = normalize_value(rec)
    assert out is not rec
    assert rec == {"value": "5"}


@pytest.mark.parametrize("bad", [None, 5, 1.5])
def test_normalize_value_non_mapping_record_raises_type_error(bad):
    """dict(record) raises TypeError for non-iterable, non-mapping records."""
    with pytest.raises(TypeError):
        normalize_value(bad)


def test_normalize_value_bad_string_record_raises_value_error():
    """A string record fails in dict() with ValueError (not a pair sequence)."""
    with pytest.raises(ValueError):
        normalize_value("abc")


# --------------------------------------------------------------------------
# strip_whitespace
# --------------------------------------------------------------------------


def test_strip_whitespace_strips_string_values():
    """Leading and trailing whitespace is removed from string values."""
    out = strip_whitespace({"a": "  hi  ", "b": "\tx\n"})
    assert out == {"a": "hi", "b": "x"}


def test_strip_whitespace_keeps_inner_whitespace():
    """Whitespace inside a string is not touched."""
    assert strip_whitespace({"a": " a  b "}) == {"a": "a  b"}


def test_strip_whitespace_leaves_non_strings_alone():
    """Numbers, None, lists and bools pass through, including strings inside lists."""
    rec = {"n": 5, "f": 1.5, "none": None, "lst": [" x "], "b": True}
    assert strip_whitespace(rec) == rec


def test_strip_whitespace_does_not_strip_keys():
    """Only values are stripped; keys keep their whitespace."""
    assert strip_whitespace({" k ": " v "}) == {" k ": "v"}


@pytest.mark.parametrize("raw, expected", [("", ""), ("   ", ""), ("\n\t", "")])
def test_strip_whitespace_empty_and_blank_strings(raw, expected):
    """Empty and whitespace-only strings become empty strings."""
    assert strip_whitespace({"a": raw}) == {"a": expected}


def test_strip_whitespace_empty_record():
    """An empty record returns an empty dict."""
    assert strip_whitespace({}) == {}


def test_strip_whitespace_returns_new_dict_and_does_not_mutate_input():
    """The input record keeps its original padded strings."""
    rec = {"a": " x "}
    out = strip_whitespace(rec)
    assert out is not rec
    assert rec == {"a": " x "}


@pytest.mark.parametrize("bad", [None, 5, "abc", [("a", 1)]])
def test_strip_whitespace_non_dict_record_raises_attribute_error(bad):
    """Objects without .items() raise AttributeError."""
    with pytest.raises(AttributeError):
        strip_whitespace(bad)


# --------------------------------------------------------------------------
# add_flag
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        (101, True),
        (100.01, True),
        (1000, True),
        ("150", True),
        (100, False),
        (100.0, False),
        ("100", False),
        (99, False),
        (0, False),
        (-5, False),
        ("-500", False),
        (False, False),
    ],
)
def test_add_flag_threshold(raw, expected):
    """flagged is True only when float(value) is strictly greater than 100."""
    assert add_flag({"value": raw})["flagged"] is expected


def test_add_flag_missing_value_is_not_flagged():
    """A record without 'value' is treated as 0 and not flagged."""
    assert add_flag({"id": 1}) == {"id": 1, "flagged": False}


def test_add_flag_empty_record():
    """An empty record gets flagged False."""
    assert add_flag({}) == {"flagged": False}


def test_add_flag_preserves_value_and_other_fields():
    """The original value is not rewritten; other fields remain."""
    assert add_flag({"value": "200", "id": 3}) == {
        "value": "200",
        "id": 3,
        "flagged": True,
    }


def test_add_flag_overwrites_existing_flag():
    """An existing 'flagged' field is replaced by the computed one."""
    assert add_flag({"value": 1, "flagged": True})["flagged"] is False


def test_add_flag_nan_is_not_flagged():
    """NaN compares False against 100."""
    assert add_flag({"value": "nan"})["flagged"] is False


@pytest.mark.parametrize("raw", ["abc", "", "  "])
def test_add_flag_non_numeric_string_raises_value_error(raw):
    """Unlike normalize_value, add_flag does not catch ValueError."""
    with pytest.raises(ValueError):
        add_flag({"value": raw})


@pytest.mark.parametrize("raw", [None, [1], {"a": 1}])
def test_add_flag_non_numeric_type_raises_type_error(raw):
    """Unlike normalize_value, add_flag does not catch TypeError."""
    with pytest.raises(TypeError):
        add_flag({"value": raw})


def test_add_flag_returns_new_dict_and_does_not_mutate_input():
    """The input record gains no 'flagged' key."""
    rec = {"value": 500}
    out = add_flag(rec)
    assert out is not rec
    assert "flagged" not in rec


# --------------------------------------------------------------------------
# apply: normal cases
# --------------------------------------------------------------------------


def test_apply_single_step():
    """One step is applied to every record."""
    out = apply([{"value": "1"}, {"value": "2"}], ["normalize_value"])
    assert out == [{"value": 1.0}, {"value": 2.0}]


def test_apply_each_builtin_step_by_name():
    """Each built-in step, called through apply, matches calling it directly."""
    recs = [{"value": " 150 ", "name": " a "}]
    for name, fn in [
        ("normalize_value", normalize_value),
        ("strip_whitespace", strip_whitespace),
        ("add_flag", add_flag),
    ]:
        assert apply(recs, [name]) == [fn(recs[0])]


def test_apply_multiple_steps_output():
    """Several steps combine: strip, normalize, then flag."""
    recs = [
        {"name": "  a ", "value": " 150 "},
        {"name": "b", "value": "oops"},
        {"name": " c", "value": 100},
    ]
    out = apply(recs, ["strip_whitespace", "normalize_value", "add_flag"])
    assert out == [
        {"name": "a", "value": 150.0, "flagged": True},
        {"name": "b", "value": 0.0, "flagged": False},
        {"name": "c", "value": 100.0, "flagged": False},
    ]


def test_apply_preserves_record_order_and_count():
    """Output has one record per input, in the same order."""
    recs = [{"id": i, "value": i} for i in range(5)]
    out = apply(recs, ["normalize_value"])
    assert [r["id"] for r in out] == [0, 1, 2, 3, 4]


def test_apply_step_order_matters_with_builtins():
    """add_flag before normalize_value raises on 'abc'; the reverse order succeeds."""
    recs = [{"value": "abc"}]
    assert apply(recs, ["normalize_value", "add_flag"]) == [
        {"value": 0.0, "flagged": False}
    ]
    with pytest.raises(ValueError):
        apply(recs, ["add_flag", "normalize_value"])


def test_apply_runs_steps_in_given_order_and_each_step_over_all_records(monkeypatch):
    """Steps run one at a time over the whole list, in the order listed."""
    calls = []
    registry = dict(transformer._REGISTRY)

    def make(tag):
        def step(record):
            calls.append((tag, record["id"]))
            return {**record, "trail": record.get("trail", "") + tag}
        return step

    registry["A"] = make("A")
    registry["B"] = make("B")
    monkeypatch.setattr(transformer, "_REGISTRY", registry)

    out = apply([{"id": 1}, {"id": 2}], ["B", "A"])
    assert calls == [("B", 1), ("B", 2), ("A", 1), ("A", 2)]
    assert [r["trail"] for r in out] == ["BA", "BA"]


# --------------------------------------------------------------------------
# apply: boundaries
# --------------------------------------------------------------------------


def test_apply_empty_records_with_steps():
    """No records gives an empty list."""
    assert apply([], ["normalize_value", "add_flag"]) == []


def test_apply_empty_records_and_empty_steps():
    """Both inputs empty gives an empty list."""
    assert apply([], []) == []


def test_apply_empty_steps_returns_equal_records():
    """With no steps the records come back unchanged."""
    recs = [{"value": "x"}, {"a": 1}]
    assert apply(recs, []) == recs


def test_apply_missing_fields_across_steps():
    """Records lacking 'value' or string fields are handled by the built-ins."""
    out = apply([{}], ["strip_whitespace", "normalize_value", "add_flag"])
    assert out == [{"value": 0.0, "flagged": False}]


def test_apply_empty_strings():
    """An empty-string value normalizes to 0.0 and is not flagged."""
    out = apply([{"value": "", "name": ""}], ["strip_whitespace", "normalize_value", "add_flag"])
    assert out == [{"value": 0.0, "name": "", "flagged": False}]


@pytest.mark.parametrize("raw, flagged", [(0, False), (-1, False), ("-250", False), (101, True)])
def test_apply_zero_and_negative_numbers(raw, flagged):
    """Zero and negative values flow through and are never flagged."""
    out = apply([{"value": raw}], ["normalize_value", "add_flag"])
    assert out[0]["value"] == float(raw)
    assert out[0]["flagged"] is flagged


def test_apply_duplicate_step_names_run_twice(monkeypatch):
    """A step name listed twice is applied twice."""
    registry = dict(transformer._REGISTRY)
    registry["inc"] = lambda r: {**r, "n": r.get("n", 0) + 1}
    monkeypatch.setattr(transformer, "_REGISTRY", registry)
    assert apply([{}], ["inc", "inc", "inc"]) == [{"n": 3}]


def test_apply_duplicate_builtin_steps_are_idempotent():
    """Repeating strip_whitespace gives the same result as running it once."""
    recs = [{"a": " x "}]
    assert apply(recs, ["strip_whitespace"] * 2) == apply(recs, ["strip_whitespace"])


def test_apply_with_tuple_of_steps_and_records():
    """Any iterable works for records, and steps are iterated twice, so tuples work."""
    assert apply(({"value": "1"},), ("normalize_value",)) == [{"value": 1.0}]


# --------------------------------------------------------------------------
# apply: mutation
# --------------------------------------------------------------------------


def test_apply_does_not_mutate_input_list_or_records():
    """Neither the input list nor its dicts change after apply with real steps."""
    recs = [{"name": " a ", "value": "150"}, {"name": "b"}]
    snapshot = copy.deepcopy(recs)
    out = apply(recs, ["strip_whitespace", "normalize_value", "add_flag"])
    assert recs == snapshot
    assert out is not recs
    for before, after in zip(recs, out):
        assert before is not after


def test_apply_returns_new_list_even_with_no_steps():
    """With no steps the result is a new list object."""
    recs = [{"a": 1}]
    out = apply(recs, [])
    assert out is not recs
    assert out == recs


def test_apply_no_steps_shares_record_objects():
    """With no steps the dicts are the same objects, so the copy is shallow."""
    rec = {"a": 1}
    out = apply([rec], [])
    assert out[0] is rec


def test_apply_shallow_copy_shares_nested_values():
    """Built-in steps copy only the top-level dict; nested lists are shared."""
    nested = [1, 2]
    rec = {"value": 1, "items": nested}
    out = apply([rec], ["normalize_value"])
    assert out[0]["items"] is nested
    out[0]["items"].append(3)
    assert rec["items"] == [1, 2, 3]


def test_apply_mutating_custom_step_changes_input(monkeypatch):
    """apply adds no copying of its own: a step that mutates in place changes the input."""
    registry = dict(transformer._REGISTRY)

    def mutator(record):
        record["touched"] = True
        return record

    registry["mutator"] = mutator
    monkeypatch.setattr(transformer, "_REGISTRY", registry)
    rec = {"a": 1}
    apply([rec], ["mutator"])
    assert rec == {"a": 1, "touched": True}


# --------------------------------------------------------------------------
# apply: error paths
# --------------------------------------------------------------------------


def test_apply_unknown_step_raises_value_error():
    """An unregistered name raises ValueError naming it."""
    with pytest.raises(ValueError, match=r"Unknown transformations: \['nope'\]"):
        apply([{"value": 1}], ["nope"])


def test_apply_reports_all_unknown_steps_in_order_with_duplicates():
    """The message lists every unknown entry in order, including repeats."""
    with pytest.raises(ValueError) as exc:
        apply([], ["x", "normalize_value", "y", "x"])
    assert str(exc.value) == "Unknown transformations: ['x', 'y', 'x']"


def test_apply_unknown_step_checked_before_any_work(monkeypatch):
    """Validation happens up front, so valid steps before the bad one never run."""
    calls = []
    registry = dict(transformer._REGISTRY)
    registry["spy"] = lambda r: calls.append(r) or r
    monkeypatch.setattr(transformer, "_REGISTRY", registry)
    with pytest.raises(ValueError):
        apply([{"a": 1}], ["spy", "missing"])
    assert calls == []


def test_apply_unknown_step_raises_even_with_empty_records():
    """The unknown-step check does not depend on the records."""
    with pytest.raises(ValueError):
        apply([], ["missing"])


@pytest.mark.parametrize("name", ["", "Normalize_Value", " add_flag", "add_flag "])
def test_apply_step_names_are_exact_match(name):
    """Names are case and whitespace sensitive."""
    with pytest.raises(ValueError):
        apply([{}], [name])


def test_apply_step_error_propagates_from_add_flag():
    """A ValueError raised inside a step is not wrapped or swallowed."""
    with pytest.raises(ValueError, match="could not convert"):
        apply([{"value": "abc"}], ["add_flag"])


def test_apply_step_type_error_propagates():
    """A TypeError raised inside a step propagates unchanged."""
    with pytest.raises(TypeError):
        apply([{"value": None}], ["add_flag"])


def test_apply_custom_step_key_error_propagates(monkeypatch):
    """A KeyError from a step reading a missing field is not caught by apply."""
    registry = dict(transformer._REGISTRY)
    registry["needs_id"] = lambda r: {**r, "id2": r["id"]}
    monkeypatch.setattr(transformer, "_REGISTRY", registry)
    with pytest.raises(KeyError):
        apply([{"a": 1}], ["needs_id"])


def test_apply_error_in_later_record_discards_partial_result():
    """An error on any record aborts apply; no partial list is returned."""
    recs = [{"value": 1}, {"value": "bad"}]
    with pytest.raises(ValueError):
        apply(recs, ["add_flag"])


# --------------------------------------------------------------------------
# apply: type errors
# --------------------------------------------------------------------------


@pytest.mark.parametrize("bad_step", [None, 5, 1.5, normalize_value, len, object])
def test_apply_hashable_non_string_step_is_unknown(bad_step):
    """Hashable non-string entries (including callables) are not in the registry."""
    with pytest.raises(ValueError, match="Unknown transformations"):
        apply([{}], [bad_step])


def test_apply_callable_step_is_not_invoked():
    """A callable passed directly is rejected, never called."""
    called = []

    def fn(record):
        called.append(record)
        return record

    with pytest.raises(ValueError):
        apply([{}], [fn])
    assert called == []


@pytest.mark.parametrize("bad_step", [["normalize_value"], {"a": 1}, {1}])
def test_apply_unhashable_step_raises_type_error(bad_step):
    """Unhashable entries fail the registry lookup with TypeError."""
    with pytest.raises(TypeError):
        apply([{}], [bad_step])


def test_apply_string_steps_is_iterated_per_character():
    """A bare string for steps is treated as a sequence of single characters."""
    with pytest.raises(ValueError) as exc:
        apply([{}], "add_flag")
    assert "'a'" in str(exc.value)


def test_apply_none_steps_raises_type_error():
    """steps=None is not iterable."""
    with pytest.raises(TypeError):
        apply([{}], None)


def test_apply_none_records_raises_type_error():
    """records=None fails in list(records)."""
    with pytest.raises(TypeError):
        apply(None, [])


def test_apply_int_records_raises_type_error():
    """A non-iterable records value fails in list(records)."""
    with pytest.raises(TypeError):
        apply(5, ["normalize_value"])


def test_apply_non_dict_record_items_fail_in_step():
    """List entries that are not dicts fail inside the step."""
    with pytest.raises(TypeError):
        apply([5], ["normalize_value"])
    with pytest.raises(AttributeError):
        apply([5], ["strip_whitespace"])


def test_apply_string_records_with_no_steps_returns_character_list():
    """A string for records is split into characters when no step runs."""
    assert apply("ab", []) == ["a", "b"]


def test_apply_dict_records_iterates_keys():
    """A dict passed as records yields its keys; with no steps they are returned."""
    assert apply({"a": 1, "b": 2}, []) == ["a", "b"]
