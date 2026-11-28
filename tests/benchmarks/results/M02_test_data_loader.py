"""Pytest suite for small_project/data_loader.py."""

import json
import sys
from pathlib import Path

SMALL_PROJECT_DIR = (
    Path(__file__).resolve().parent.parent / "sample_jobs" / "small_project"
)
sys.path.insert(0, str(SMALL_PROJECT_DIR))

import pytest  # noqa: E402

import data_loader  # noqa: E402
from data_loader import REQUIRED_COLUMNS, load, load_csv, load_json  # noqa: E402

HEADER = "id,name,value,timestamp"


def write_csv(path, text, encoding="utf-8"):
    """Write raw CSV text to path with no newline translation."""
    with open(path, "w", newline="", encoding=encoding) as fh:
        fh.write(text)
    return str(path)


def write_json(path, obj, encoding="utf-8"):
    """Write obj as JSON text to path."""
    with open(path, "w", encoding=encoding) as fh:
        json.dump(obj, fh, ensure_ascii=False)
    return str(path)


# ---------------------------------------------------------------- constants


def test_required_columns_constant():
    """REQUIRED_COLUMNS holds exactly id, name, value and timestamp."""
    assert REQUIRED_COLUMNS == {"id", "name", "value", "timestamp"}


# ----------------------------------------------------------------- load_csv


def test_load_csv_multiple_rows(tmp_path):
    """load_csv returns one dict per row with all values as strings."""
    p = write_csv(tmp_path / "d.csv", f"{HEADER}\n1,a,10,2026-01-01\n2,b,20,2026-01-02\n")
    assert load_csv(p) == [
        {"id": "1", "name": "a", "value": "10", "timestamp": "2026-01-01"},
        {"id": "2", "name": "b", "value": "20", "timestamp": "2026-01-02"},
    ]


def test_load_csv_returns_plain_dicts(tmp_path):
    """load_csv returns a list of plain dict objects."""
    p = write_csv(tmp_path / "d.csv", f"{HEADER}\n1,a,10,t\n")
    result = load_csv(p)
    assert isinstance(result, list)
    assert type(result[0]) is dict


def test_load_csv_accepts_path_object(tmp_path):
    """load_csv accepts a pathlib.Path because open() does."""
    p = tmp_path / "d.csv"
    write_csv(p, f"{HEADER}\n1,a,10,t\n")
    assert len(load_csv(p)) == 1


def test_load_csv_single_record(tmp_path):
    """A CSV with one data row yields a list of length one."""
    p = write_csv(tmp_path / "d.csv", f"{HEADER}\n1,a,10,t\n")
    assert load_csv(p) == [{"id": "1", "name": "a", "value": "10", "timestamp": "t"}]


def test_load_csv_header_only(tmp_path):
    """A header-only CSV with all required columns returns an empty list."""
    p = write_csv(tmp_path / "d.csv", f"{HEADER}\n")
    assert load_csv(p) == []


def test_load_csv_header_only_without_trailing_newline(tmp_path):
    """A header line without a trailing newline still returns an empty list."""
    p = write_csv(tmp_path / "d.csv", HEADER)
    assert load_csv(p) == []


def test_load_csv_extra_columns_are_kept(tmp_path):
    """Columns beyond the required ones are preserved in each row dict."""
    p = write_csv(tmp_path / "d.csv", f"{HEADER},extra\n1,a,10,t,x\n")
    assert load_csv(p) == [
        {"id": "1", "name": "a", "value": "10", "timestamp": "t", "extra": "x"}
    ]


def test_load_csv_column_order_does_not_matter(tmp_path):
    """Required columns may appear in any order."""
    p = write_csv(tmp_path / "d.csv", "timestamp,value,name,id\nt,10,a,1\n")
    assert load_csv(p) == [{"timestamp": "t", "value": "10", "name": "a", "id": "1"}]


def test_load_csv_short_row_fills_none(tmp_path):
    """A row with fewer fields than the header gets None for the missing ones."""
    p = write_csv(tmp_path / "d.csv", f"{HEADER}\n1,a\n")
    assert load_csv(p) == [{"id": "1", "name": "a", "value": None, "timestamp": None}]


def test_load_csv_long_row_goes_under_none_key(tmp_path):
    """Surplus fields in a row are collected in a list under the None key."""
    p = write_csv(tmp_path / "d.csv", f"{HEADER}\n1,a,10,t,extra1,extra2\n")
    row = load_csv(p)[0]
    assert row[None] == ["extra1", "extra2"]
    assert row["id"] == "1"


def test_load_csv_blank_lines_are_skipped(tmp_path):
    """DictReader skips completely blank lines between rows."""
    p = write_csv(tmp_path / "d.csv", f"{HEADER}\n\n1,a,10,t\n\n2,b,20,u\n")
    assert [r["id"] for r in load_csv(p)] == ["1", "2"]


def test_load_csv_quoted_field_with_comma_and_newline(tmp_path):
    """Quoted fields keep embedded commas and newlines intact."""
    p = write_csv(tmp_path / "d.csv", f'{HEADER}\n1,"a, b","line1\nline2",t\n')
    row = load_csv(p)[0]
    assert row["name"] == "a, b"
    assert row["value"] == "line1\nline2"


def test_load_csv_crlf_line_endings(tmp_path):
    """CRLF line endings are handled because the file is opened with newline=''."""
    p = write_csv(tmp_path / "d.csv", f"{HEADER}\r\n1,a,10,t\r\n")
    assert load_csv(p) == [{"id": "1", "name": "a", "value": "10", "timestamp": "t"}]


def test_load_csv_unicode_content(tmp_path):
    """Non-ASCII text in CSV values is returned unchanged."""
    import locale

    if locale.getpreferredencoding(False).lower().replace("-", "") != "utf8":
        pytest.skip("open() uses the locale encoding, which is not UTF-8 here")
    p = write_csv(tmp_path / "d.csv", f"{HEADER}\n1,Zoë 日本語,€5,t\n")
    row = load_csv(p)[0]
    assert row["name"] == "Zoë 日本語"
    assert row["value"] == "€5"


def test_load_csv_does_not_check_file_extension(tmp_path):
    """load_csv reads any file as CSV regardless of its extension."""
    p = write_csv(tmp_path / "data.txt", f"{HEADER}\n1,a,10,t\n")
    assert len(load_csv(p)) == 1


def test_load_csv_empty_file_raises_missing_all_columns(tmp_path):
    """An empty file has no header, so every required column is reported missing."""
    p = write_csv(tmp_path / "d.csv", "")
    with pytest.raises(ValueError) as exc:
        load_csv(p)
    assert str(exc.value) == (
        "CSV missing required columns: ['id', 'name', 'timestamp', 'value']"
    )


def test_load_csv_missing_one_column(tmp_path):
    """The error message lists the single missing column."""
    p = write_csv(tmp_path / "d.csv", "id,name,value\n1,a,10\n")
    with pytest.raises(ValueError) as exc:
        load_csv(p)
    assert str(exc.value) == "CSV missing required columns: ['timestamp']"


def test_load_csv_missing_columns_listed_sorted(tmp_path):
    """Missing columns appear in alphabetical order in the error message."""
    p = write_csv(tmp_path / "d.csv", "name\na\n")
    with pytest.raises(ValueError) as exc:
        load_csv(p)
    assert str(exc.value) == "CSV missing required columns: ['id', 'timestamp', 'value']"


def test_load_csv_column_names_are_case_sensitive(tmp_path):
    """Upper-case header names do not satisfy the lower-case requirement."""
    p = write_csv(tmp_path / "d.csv", "ID,NAME,VALUE,TIMESTAMP\n1,a,10,t\n")
    with pytest.raises(ValueError, match="missing required columns"):
        load_csv(p)


def test_load_csv_header_whitespace_is_not_stripped(tmp_path):
    """A header such as ' name' with a leading space does not match 'name'."""
    p = write_csv(tmp_path / "d.csv", "id, name,value,timestamp\n1,a,10,t\n")
    with pytest.raises(ValueError) as exc:
        load_csv(p)
    assert "'name'" in str(exc.value)


def test_load_csv_missing_file_raises_file_not_found(tmp_path):
    """A path that does not exist raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_csv(str(tmp_path / "nope.csv"))


def test_load_csv_directory_raises_is_a_directory(tmp_path):
    """Passing a directory raises IsADirectoryError."""
    with pytest.raises(IsADirectoryError):
        load_csv(str(tmp_path))


@pytest.mark.parametrize("bad", [None, 3.5, [], {}, object()])
def test_load_csv_wrong_path_type_raises_type_error(bad):
    """load_csv raises TypeError when the path is not str, bytes, int or PathLike."""
    with pytest.raises(TypeError):
        load_csv(bad)


# ---------------------------------------------------------------- load_json


def test_load_json_list_of_records(tmp_path):
    """load_json returns the parsed list of dicts as-is."""
    data = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
    p = write_json(tmp_path / "d.json", data)
    assert load_json(p) == data


def test_load_json_preserves_native_types(tmp_path):
    """JSON numbers, booleans and null keep their Python types."""
    data = [{"id": 1, "value": 1.5, "ok": True, "none": None}]
    p = write_json(tmp_path / "d.json", data)
    result = load_json(p)
    assert result == data
    assert result[0]["ok"] is True
    assert result[0]["none"] is None


def test_load_json_accepts_path_object(tmp_path):
    """load_json accepts a pathlib.Path because open() does."""
    p = tmp_path / "d.json"
    write_json(p, [{"id": 1}])
    assert load_json(p) == [{"id": 1}]


def test_load_json_single_record(tmp_path):
    """A one-element JSON array returns a list of length one."""
    p = write_json(tmp_path / "d.json", [{"id": 1}])
    assert load_json(p) == [{"id": 1}]


def test_load_json_empty_list(tmp_path):
    """An empty JSON array returns an empty list."""
    p = write_json(tmp_path / "d.json", [])
    assert load_json(p) == []


def test_load_json_does_not_validate_required_columns(tmp_path):
    """load_json performs no column check, so records can have any keys."""
    p = write_json(tmp_path / "d.json", [{"anything": "goes"}])
    assert load_json(p) == [{"anything": "goes"}]


def test_load_json_does_not_validate_element_types(tmp_path):
    """load_json only checks the top-level type, so non-dict elements pass."""
    p = write_json(tmp_path / "d.json", [1, "two", None, [3]])
    assert load_json(p) == [1, "two", None, [3]]


def test_load_json_does_not_check_file_extension(tmp_path):
    """load_json reads any file as JSON regardless of its extension."""
    p = write_json(tmp_path / "data.txt", [{"id": 1}])
    assert load_json(p) == [{"id": 1}]


def test_load_json_unicode_content(tmp_path):
    """Non-ASCII text in JSON values is returned unchanged."""
    import locale

    if locale.getpreferredencoding(False).lower().replace("-", "") != "utf8":
        pytest.skip("open() uses the locale encoding, which is not UTF-8 here")
    p = write_json(tmp_path / "d.json", [{"name": "Zoë 日本語 €"}])
    assert load_json(p) == [{"name": "Zoë 日本語 €"}]


def test_load_json_escaped_unicode_content(tmp_path):
    """JSON \\u escapes decode to real characters regardless of locale."""
    p = tmp_path / "d.json"
    p.write_text('[{"name": "Zo\\u00eb"}]', encoding="ascii")
    assert load_json(str(p)) == [{"name": "Zoë"}]


@pytest.mark.parametrize(
    "content, type_name",
    [
        ('{"id": 1}', "dict"),
        ('"text"', "str"),
        ("42", "int"),
        ("4.5", "float"),
        ("true", "bool"),
        ("null", "NoneType"),
    ],
)
def test_load_json_non_list_raises_value_error(tmp_path, content, type_name):
    """A JSON document whose top level is not an array raises ValueError naming the type."""
    p = tmp_path / "d.json"
    p.write_text(content)
    with pytest.raises(ValueError) as exc:
        load_json(str(p))
    assert str(exc.value) == f"Expected a JSON array, got {type_name}"


def test_load_json_malformed_raises_json_decode_error(tmp_path):
    """Malformed JSON raises json.JSONDecodeError."""
    p = tmp_path / "d.json"
    p.write_text("[{'id': 1}")
    with pytest.raises(json.JSONDecodeError):
        load_json(str(p))


def test_load_json_decode_error_is_a_value_error(tmp_path):
    """JSONDecodeError subclasses ValueError, so callers can catch ValueError for both."""
    p = tmp_path / "d.json"
    p.write_text("[1, 2,")
    with pytest.raises(ValueError):
        load_json(str(p))


def test_load_json_empty_file_raises_json_decode_error(tmp_path):
    """A zero-byte file is not valid JSON and raises JSONDecodeError."""
    p = tmp_path / "d.json"
    p.write_text("")
    with pytest.raises(json.JSONDecodeError):
        load_json(str(p))


def test_load_json_trailing_garbage_raises_json_decode_error(tmp_path):
    """Extra data after a valid array raises JSONDecodeError."""
    p = tmp_path / "d.json"
    p.write_text("[1] [2]")
    with pytest.raises(json.JSONDecodeError):
        load_json(str(p))


def test_load_json_missing_file_raises_file_not_found(tmp_path):
    """A path that does not exist raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_json(str(tmp_path / "nope.json"))


def test_load_json_directory_raises_is_a_directory(tmp_path):
    """Passing a directory raises IsADirectoryError."""
    with pytest.raises(IsADirectoryError):
        load_json(str(tmp_path))


@pytest.mark.parametrize("bad", [None, 3.5, [], {}, object()])
def test_load_json_wrong_path_type_raises_type_error(bad):
    """load_json raises TypeError when the path is not str, bytes, int or PathLike."""
    with pytest.raises(TypeError):
        load_json(bad)


# --------------------------------------------------------------------- load


def test_load_dispatches_csv(tmp_path):
    """load routes a .csv path to load_csv and returns its rows."""
    p = write_csv(tmp_path / "d.csv", f"{HEADER}\n1,a,10,t\n")
    assert load(p) == [{"id": "1", "name": "a", "value": "10", "timestamp": "t"}]


def test_load_dispatches_json(tmp_path):
    """load routes a .json path to load_json and returns its records."""
    p = write_json(tmp_path / "d.json", [{"id": 1}])
    assert load(p) == [{"id": 1}]


def test_load_accepts_path_object(tmp_path):
    """load accepts a pathlib.Path since Path(path) and open() both do."""
    p = tmp_path / "d.json"
    write_json(p, [{"id": 1}])
    assert load(p) == [{"id": 1}]


def test_load_calls_the_right_loader(tmp_path, monkeypatch):
    """load calls load_csv for .csv and load_json for .json, passing the path through."""
    calls = []
    monkeypatch.setattr(data_loader, "load_csv", lambda p: calls.append(("csv", p)) or "C")
    monkeypatch.setattr(data_loader, "load_json", lambda p: calls.append(("json", p)) or "J")
    assert load("x.csv") == "C"
    assert load("x.json") == "J"
    assert calls == [("csv", "x.csv"), ("json", "x.json")]


def test_load_csv_empty_list_boundary_via_load(tmp_path):
    """load on a header-only .csv returns an empty list."""
    p = write_csv(tmp_path / "d.csv", f"{HEADER}\n")
    assert load(p) == []


def test_load_empty_json_list_via_load(tmp_path):
    """load on a .json file holding [] returns an empty list."""
    p = write_json(tmp_path / "d.json", [])
    assert load(p) == []


def test_load_propagates_csv_validation_error(tmp_path):
    """load lets the missing-column ValueError from load_csv propagate."""
    p = write_csv(tmp_path / "d.csv", "id\n1\n")
    with pytest.raises(ValueError, match="CSV missing required columns"):
        load(p)


def test_load_propagates_json_shape_error(tmp_path):
    """load lets the not-an-array ValueError from load_json propagate."""
    p = tmp_path / "d.json"
    p.write_text("{}")
    with pytest.raises(ValueError, match="Expected a JSON array, got dict"):
        load(str(p))


def test_load_propagates_json_decode_error(tmp_path):
    """load lets JSONDecodeError from a malformed .json file propagate."""
    p = tmp_path / "d.json"
    p.write_text("not json")
    with pytest.raises(json.JSONDecodeError):
        load(str(p))


def test_load_missing_csv_raises_file_not_found(tmp_path):
    """load on a nonexistent .csv path raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load(str(tmp_path / "nope.csv"))


def test_load_missing_json_raises_file_not_found(tmp_path):
    """load on a nonexistent .json path raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load(str(tmp_path / "nope.json"))


@pytest.mark.parametrize("name", ["d.txt", "d.xml", "d.csv.bak", "d.jsonl", "d.tsv"])
def test_load_unsupported_extension_raises_value_error(tmp_path, name):
    """load raises ValueError for extensions other than .csv and .json."""
    p = tmp_path / name
    p.write_text("whatever")
    suffix = Path(name).suffix
    with pytest.raises(ValueError) as exc:
        load(str(p))
    assert str(exc.value) == f"Unsupported file type: {suffix}"


@pytest.mark.parametrize("name", ["d.CSV", "d.JSON", "d.Csv", "d.Json"])
def test_load_uppercase_extension_is_unsupported(tmp_path, name):
    """Extension matching is case-sensitive, so .CSV and .JSON are rejected."""
    p = tmp_path / name
    p.write_text("[]")
    with pytest.raises(ValueError, match="Unsupported file type"):
        load(str(p))


def test_load_no_extension_raises_value_error(tmp_path):
    """A file with no extension raises ValueError with an empty suffix in the message."""
    p = tmp_path / "data"
    p.write_text("[]")
    with pytest.raises(ValueError) as exc:
        load(str(p))
    assert str(exc.value) == "Unsupported file type: "


def test_load_dotfile_without_suffix_is_unsupported(tmp_path):
    """A name like '.csv' has no suffix in pathlib terms, so it is rejected."""
    p = tmp_path / ".csv"
    p.write_text(f"{HEADER}\n")
    with pytest.raises(ValueError) as exc:
        load(str(p))
    assert str(exc.value) == "Unsupported file type: "


def test_load_only_last_suffix_counts(tmp_path):
    """For 'd.backup.json' the suffix is '.json', so load_json is used."""
    p = write_json(tmp_path / "d.backup.json", [{"id": 1}])
    assert load(p) == [{"id": 1}]


def test_load_unsupported_extension_checked_before_file_exists(tmp_path):
    """The extension check runs before any file access, so a missing .txt gives ValueError."""
    with pytest.raises(ValueError, match="Unsupported file type: .txt"):
        load(str(tmp_path / "nope.txt"))


def test_load_empty_string_path_is_unsupported():
    """An empty string has no suffix and raises the unsupported-type ValueError."""
    with pytest.raises(ValueError, match="Unsupported file type"):
        load("")


@pytest.mark.parametrize("bad", [None, 42, 3.5, [], {}, object()])
def test_load_wrong_path_type_raises_type_error(bad):
    """load raises TypeError from Path() when given None, numbers or containers."""
    with pytest.raises(TypeError):
        load(bad)


def test_load_bytes_path_raises_type_error(tmp_path):
    """load rejects bytes paths because pathlib.Path does not accept bytes."""
    with pytest.raises(TypeError):
        load(str(tmp_path / "d.csv").encode())
