import copy
import sys
from pathlib import Path

import pytest

sys.dont_write_bytecode = True
_SRC = Path(__file__).resolve().parent.parent / "sample_jobs" / "small_project"
sys.path.insert(0, str(_SRC))

import transformer  # noqa: E402
from transformer import add_flag, apply, normalize_value, register, strip_whitespace  # noqa: E402


# register

def test_register_returns_function_and_stores_it():
    def fn(r):
        return r

    try:
        assert register("_x03_tmp")(fn) is fn
        assert transformer._REGISTRY["_x03_tmp"] is fn
    finally:
        transformer._REGISTRY.pop("_x03_tmp", None)


@pytest.mark.parametrize("name", ["normalize_value", "strip_whitespace", "add_flag"])
def test_builtin_transformations_registered(name):
    assert name in transformer._REGISTRY


# normalize_value

@pytest.mark.parametrize(
    "record, expected",
    [
        ({"value": "12.5"}, 12.5),
        ({"value": 3}, 3.0),
        ({"value": " 7 "}, 7.0),
        ({"value": "abc"}, 0.0),
        ({"value": ""}, 0.0),
        ({"value": None}, 0.0),
        ({"value": [1]}, 0.0),
        ({}, 0.0),
    ],
)
def test_normalize_value(record, expected):
    out = normalize_value(record)
    assert out["value"] == expected
    assert isinstance(out["value"], float)


def test_normalize_value_keeps_other_fields_and_does_not_mutate():
    rec = {"id": "a", "value": "5"}
    snapshot = copy.deepcopy(rec)
    out = normalize_value(rec)
    assert out["id"] == "a"
    assert rec == snapshot
    assert out is not rec


# strip_whitespace

@pytest.mark.parametrize(
    "record, expected",
    [
        ({"a": "  hi  ", "b": "x"}, {"a": "hi", "b": "x"}),
        ({"a": 5, "b": None, "c": " y "}, {"a": 5, "b": None, "c": "y"}),
        ({"a": ["  keep  "]}, {"a": ["  keep  "]}),
        ({"a": "   "}, {"a": ""}),
        ({}, {}),
    ],
)
def test_strip_whitespace(record, expected):
    assert strip_whitespace(record) == expected


def test_strip_whitespace_does_not_mutate():
    rec = {"a": "  hi  "}
    out = strip_whitespace(rec)
    assert rec == {"a": "  hi  "}
    assert out is not rec


# add_flag

@pytest.mark.parametrize(
    "record, expected",
    [
        ({"value": 101}, True),
        ({"value": 100}, False),
        ({"value": 100.01}, True),
        ({"value": "250"}, True),
        ({"value": "5"}, False),
        ({"value": -500}, False),
        ({}, False),
    ],
)
def test_add_flag(record, expected):
    assert add_flag(record)["flagged"] is expected


def test_add_flag_does_not_mutate():
    rec = {"value": 200}
    out = add_flag(rec)
    assert "flagged" not in rec
    assert out["flagged"] is True


@pytest.mark.parametrize(
    "value, exc",
    [("abc", ValueError), ("", ValueError), (None, TypeError), ([1], TypeError)],
)
def test_add_flag_bad_value_raises(value, exc):
    with pytest.raises(exc):
        add_flag({"value": value})


@pytest.mark.xfail(
    reason="add_flag does not guard float() like normalize_value does: "
    "non-numeric 'value' raises instead of being treated as 0",
    raises=ValueError,
    strict=True,
)
def test_add_flag_non_numeric_string_should_not_raise():
    assert add_flag({"value": "abc"})["flagged"] is False


# apply

def test_apply_empty_records():
    assert apply([], ["normalize_value", "add_flag"]) == []


def test_apply_empty_steps_returns_copy_of_list_sharing_records():
    recs = [{"value": 1}]
    out = apply(recs, [])
    assert out == recs
    assert out is not recs
    assert out[0] is recs[0]


def test_apply_typical_chain():
    recs = [{"name": "  a ", "value": " 150 "}, {"name": "b", "value": "x"}]
    out = apply(recs, ["strip_whitespace", "normalize_value", "add_flag"])
    assert out == [
        {"name": "a", "value": 150.0, "flagged": True},
        {"name": "b", "value": 0.0, "flagged": False},
    ]


def test_apply_does_not_mutate_inputs():
    recs = [{"name": " a ", "value": "150"}]
    snapshot = copy.deepcopy(recs)
    steps = ["strip_whitespace", "normalize_value", "add_flag"]
    apply(recs, steps)
    assert recs == snapshot
    assert steps == ["strip_whitespace", "normalize_value", "add_flag"]


def test_apply_order_matters():
    recs = [{"value": "abc"}]
    assert apply(recs, ["normalize_value", "add_flag"]) == [{"value": 0.0, "flagged": False}]
    with pytest.raises(ValueError):
        apply(recs, ["add_flag", "normalize_value"])


@pytest.mark.parametrize(
    "steps, bad",
    [
        (["nope"], ["nope"]),
        (["normalize_value", "nope", "also_nope"], ["nope", "also_nope"]),
    ],
)
def test_apply_unknown_step(steps, bad):
    with pytest.raises(ValueError, match="Unknown transformations") as ei:
        apply([{"value": 1}], steps)
    assert str(bad) in str(ei.value)


def test_apply_unknown_step_raises_even_with_empty_records():
    with pytest.raises(ValueError):
        apply([], ["nope"])


def test_apply_missing_keys_use_defaults():
    assert apply([{}], ["normalize_value", "add_flag"]) == [{"value": 0.0, "flagged": False}]


def test_apply_propagates_transformation_errors():
    with pytest.raises(ValueError):
        apply([{"value": "abc"}], ["add_flag"])
