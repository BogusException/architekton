"""Unit tests for the ORIGINAL small_project data_loader module."""

import json
import sys
from pathlib import Path

import pytest

SMALL_PROJECT = Path(__file__).resolve().parent.parent / "sample_jobs" / "small_project"
sys.path.insert(0, str(SMALL_PROJECT))

import data_loader  # noqa: E402

HEADER = "id,name,value,timestamp\n"
ROW_A = "1,alpha,10,2026-01-01T00:00:00\n"
ROW_B = "2,beta,20,2026-01-02T00:00:00\n"


def write_csv(tmp_path, text, name="data.csv", encoding="utf-8"):
    p = tmp_path / name
    p.write_bytes(text.encode(encoding))
    return str(p)


def write_json(tmp_path, obj, name="data.json"):
    p = tmp_path / name
    p.write_text(json.dumps(obj), encoding="utf-8")
    return str(p)


# ---- load_csv ----

def test_load_csv_valid(tmp_path):
    path = write_csv(tmp_path, HEADER + ROW_A + ROW_B)
    rows = data_loader.load_csv(path)
    assert rows == [
        {"id": "1", "name": "alpha", "value": "10", "timestamp": "2026-01-01T00:00:00"},
        {"id": "2", "name": "beta", "value": "20", "timestamp": "2026-01-02T00:00:00"},
    ]


def test_load_csv_header_only_returns_empty_list(tmp_path):
    assert data_loader.load_csv(write_csv(tmp_path, HEADER)) == []


def test_load_csv_keeps_extra_columns(tmp_path):
    path = write_csv(tmp_path, "id,name,value,timestamp,extra\n1,a,2,t,x\n")
    assert data_loader.load_csv(path)[0]["extra"] == "x"


def test_load_csv_column_order_does_not_matter(tmp_path):
    path = write_csv(tmp_path, "timestamp,value,name,id\nt,2,a,1\n")
    assert data_loader.load_csv(path) == [
        {"timestamp": "t", "value": "2", "name": "a", "id": "1"}
    ]


def test_load_csv_missing_required_columns(tmp_path):
    path = write_csv(tmp_path, "id,name\n1,a\n")
    with pytest.raises(ValueError, match="missing required columns") as exc:
        data_loader.load_csv(path)
    assert "['timestamp', 'value']" in str(exc.value)


def test_load_csv_column_names_are_case_sensitive(tmp_path):
    path = write_csv(tmp_path, "ID,Name,Value,Timestamp\n1,a,2,t\n")
    with pytest.raises(ValueError, match="missing required columns"):
        data_loader.load_csv(path)


def test_load_csv_short_row_gives_none_for_missing_field(tmp_path):
    path = write_csv(tmp_path, HEADER + "1,a\n")
    row = data_loader.load_csv(path)[0]
    assert row["value"] is None
    assert row["timestamp"] is None


def test_load_csv_empty_file(tmp_path):
    path = write_csv(tmp_path, "")
    with pytest.raises(ValueError, match="missing required columns"):
        data_loader.load_csv(path)


def test_load_csv_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        data_loader.load_csv(str(tmp_path / "nope.csv"))


@pytest.mark.xfail(
    reason="Bug: load_csv opens the file without encoding='utf-8-sig', so a "
    "UTF-8 BOM stays glued to the first header ('\\ufeffid') and 'id' is "
    "reported as a missing column.",
)
def test_load_csv_utf8_bom_is_accepted(tmp_path):
    path = write_csv(tmp_path, HEADER + ROW_A, encoding="utf-8-sig")
    rows = data_loader.load_csv(path)
    assert rows[0]["id"] == "1"


def test_load_csv_utf8_bom_currently_rejected(tmp_path):
    path = write_csv(tmp_path, HEADER + ROW_A, encoding="utf-8-sig")
    with pytest.raises(ValueError, match="id"):
        data_loader.load_csv(path)


# ---- load_json ----

def test_load_json_valid(tmp_path):
    records = [{"id": 1, "name": "a", "value": 2, "timestamp": "t"}]
    assert data_loader.load_json(write_json(tmp_path, records)) == records


def test_load_json_empty_array(tmp_path):
    assert data_loader.load_json(write_json(tmp_path, [])) == []


def test_load_json_does_not_check_required_columns(tmp_path):
    records = [{"unrelated": 1}]
    assert data_loader.load_json(write_json(tmp_path, records)) == records


@pytest.mark.parametrize("payload", [{"a": 1}, "text", 42, None, True])
def test_load_json_not_a_list(tmp_path, payload):
    with pytest.raises(ValueError, match="Expected a JSON array"):
        data_loader.load_json(write_json(tmp_path, payload))


def test_load_json_not_a_list_names_the_type(tmp_path):
    with pytest.raises(ValueError, match="got dict"):
        data_loader.load_json(write_json(tmp_path, {"a": 1}))


def test_load_json_empty_file(tmp_path):
    p = tmp_path / "empty.json"
    p.write_text("")
    with pytest.raises(json.JSONDecodeError):
        data_loader.load_json(str(p))


def test_load_json_malformed(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("[1, 2,")
    with pytest.raises(ValueError):
        data_loader.load_json(str(p))


def test_load_json_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        data_loader.load_json(str(tmp_path / "nope.json"))


# ---- load ----

def test_load_dispatches_csv(tmp_path):
    path = write_csv(tmp_path, HEADER + ROW_A)
    assert data_loader.load(path) == data_loader.load_csv(path)


def test_load_dispatches_json(tmp_path):
    records = [{"id": 1}]
    assert data_loader.load(write_json(tmp_path, records)) == records


@pytest.mark.parametrize("name", ["data.txt", "data.xml", "data", "data.CSV", "data.JSON"])
def test_load_unsupported_extension(tmp_path, name):
    p = tmp_path / name
    p.write_text("whatever")
    with pytest.raises(ValueError, match="Unsupported file type"):
        data_loader.load(str(p))


def test_load_missing_csv_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        data_loader.load(str(tmp_path / "nope.csv"))


def test_load_missing_json_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        data_loader.load(str(tmp_path / "nope.json"))


def test_load_empty_csv_file(tmp_path):
    with pytest.raises(ValueError, match="missing required columns"):
        data_loader.load(write_csv(tmp_path, ""))


def test_load_empty_json_file(tmp_path):
    p = tmp_path / "empty.json"
    p.write_text("")
    with pytest.raises(ValueError):
        data_loader.load(str(p))


def test_load_json_not_a_list_via_dispatch(tmp_path):
    with pytest.raises(ValueError, match="Expected a JSON array"):
        data_loader.load(write_json(tmp_path, {"a": 1}))


def test_load_bom_csv_via_dispatch_currently_rejected(tmp_path):
    path = write_csv(tmp_path, HEADER + ROW_A, encoding="utf-8-sig")
    with pytest.raises(ValueError):
        data_loader.load(path)
