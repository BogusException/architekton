"""Tests for small_project/reporter.py using real ValidationReport objects."""

import json
import sys
from pathlib import Path

SMALL_PROJECT_DIR = (
    Path(__file__).resolve().parent.parent / "sample_jobs" / "small_project"
)
sys.path.insert(0, str(SMALL_PROJECT_DIR))

import pytest  # noqa: E402

import reporter  # noqa: E402
from validator import RecordResult, ValidationReport, validate  # noqa: E402


def make_mixed_report() -> ValidationReport:
    """Build a real report with one passing and two failing records."""
    return validate(
        [
            {"id": "a", "value": 1, "name": "alpha"},
            {"id": "b", "value": -5, "name": "beta"},
            {"id": "", "value": "x", "name": " "},
        ]
    )


def make_passing_report(count: int = 3) -> ValidationReport:
    """Build a real report in which every record passes."""
    return validate(
        [{"id": str(i), "value": i, "name": f"n{i}"} for i in range(1, count + 1)]
    )


def make_failing_report(count: int = 3) -> ValidationReport:
    """Build a real report in which every record fails."""
    return validate([{"id": f"r{i}", "value": -1, "name": "ok"} for i in range(count)])


# ---------------------------------------------------------------- to_text


def test_to_text_mixed_report_lists_summary_and_failures():
    """to_text shows FAILED header, counts, and only the failing records."""
    text = reporter.to_text(make_mixed_report())
    lines = text.split("\n")
    assert lines[0] == "Validation FAILED"
    assert lines[1] == "  Total records : 3"
    assert lines[2] == "  Passed        : 1"
    assert lines[3] == "  Failed        : 2"
    assert lines[4] == ""
    assert lines[5] == "Failures:"
    assert "  Record b:" in lines
    assert "    - value_non_negative: 'value' is negative: -5" in lines
    assert "  Record a:" not in lines


def test_to_text_missing_id_uses_empty_record_id():
    """A record with an empty id string appears as 'Record :' with all its failures."""
    text = reporter.to_text(make_mixed_report())
    assert "  Record :" in text.split("\n")
    assert "    - has_id: missing or empty 'id'" in text
    assert "    - name_not_empty: missing or empty 'name'" in text
    assert "    - value_non_negative: 'value' is not numeric: 'x'" in text


def test_to_text_all_passed_has_no_failures_section():
    """A fully passing report prints PASSED and four summary lines only."""
    text = reporter.to_text(make_passing_report(3))
    assert text.split("\n") == [
        "Validation PASSED",
        "  Total records : 3",
        "  Passed        : 3",
        "  Failed        : 0",
    ]
    assert "Failures:" not in text


def test_to_text_all_failed_lists_every_record():
    """When all records fail, each one is listed under Failures."""
    report = make_failing_report(3)
    text = reporter.to_text(report)
    assert text.startswith("Validation FAILED")
    assert "  Passed        : 0" in text
    assert "  Failed        : 3" in text
    for i in range(3):
        assert f"  Record r{i}:" in text


def test_to_text_zero_records_is_passed():
    """An empty report has failed == 0, so it reports PASSED with zero counts."""
    report = validate([])
    assert reporter.to_text(report).split("\n") == [
        "Validation PASSED",
        "  Total records : 0",
        "  Passed        : 0",
        "  Failed        : 0",
    ]


def test_to_text_has_no_trailing_newline():
    """to_text joins lines with newlines and does not append a trailing one."""
    assert not reporter.to_text(make_passing_report(1)).endswith("\n")


def test_to_text_very_long_failure_message_is_not_truncated():
    """A 100k-character failure message is emitted in full."""
    long_msg = "x" * 100_000
    report = ValidationReport(
        total=1,
        passed=0,
        failed=1,
        results=[RecordResult(record_id="big", passed=False, failures=[long_msg])],
    )
    text = reporter.to_text(report)
    assert f"    - {long_msg}" in text
    assert len(text) > 100_000


def test_to_text_unicode_ids_and_messages_preserved():
    """Non-ASCII record ids and failure messages appear unchanged in text output."""
    report = ValidationReport(
        total=1,
        passed=0,
        failed=1,
        results=[
            RecordResult(
                record_id="zażółć-日本語",
                passed=False,
                failures=["nom vide: éè \U0001f600"],
            )
        ],
    )
    text = reporter.to_text(report)
    assert "  Record zażółć-日本語:" in text
    assert "    - nom vide: éè \U0001f600" in text


def test_to_text_ok_depends_on_failed_count_not_results():
    """A hand-built report with failed=0 prints PASSED even if a result failed."""
    report = ValidationReport(
        total=1,
        passed=1,
        failed=0,
        results=[RecordResult(record_id="x", passed=False, failures=["boom"])],
    )
    text = reporter.to_text(report)
    assert text.startswith("Validation PASSED")
    assert "boom" not in text


def test_to_text_failed_nonzero_with_no_failing_results_prints_empty_section():
    """failed > 0 with only passing results prints the Failures header and no records."""
    report = ValidationReport(
        total=1,
        passed=1,
        failed=1,
        results=[RecordResult(record_id="x", passed=True)],
    )
    lines = reporter.to_text(report).split("\n")
    assert lines[-2:] == ["", "Failures:"]


def test_to_text_non_string_failure_is_formatted_via_fstring():
    """Non-string failure items are rendered with str() by the f-string."""
    report = ValidationReport(
        total=1,
        passed=0,
        failed=1,
        results=[RecordResult(record_id="x", passed=False, failures=[42, None])],
    )
    lines = reporter.to_text(report).split("\n")
    assert "    - 42" in lines
    assert "    - None" in lines


# ---------------------------------------------------------------- to_json


def test_to_json_mixed_report_structure():
    """to_json emits the documented keys and per-record entries."""
    report = make_mixed_report()
    data = json.loads(reporter.to_json(report))
    assert set(data) == {"passed", "total", "pass_count", "fail_count", "records"}
    assert data["passed"] is False
    assert data["total"] == 3
    assert data["pass_count"] == 1
    assert data["fail_count"] == 2
    assert [r["id"] for r in data["records"]] == ["a", "b", ""]
    assert data["records"][0] == {"id": "a", "passed": True, "failures": []}
    assert data["records"][1]["passed"] is False
    assert data["records"][1]["failures"] == [
        "value_non_negative: 'value' is negative: -5"
    ]


def test_to_json_uses_two_space_indent():
    """to_json output is indented with two spaces."""
    out = reporter.to_json(make_passing_report(1))
    assert out.startswith('{\n  "passed": true,')


def test_to_json_all_passed():
    """A passing report has passed true and every record passed."""
    data = json.loads(reporter.to_json(make_passing_report(4)))
    assert data["passed"] is True
    assert data["pass_count"] == 4
    assert data["fail_count"] == 0
    assert all(r["passed"] and r["failures"] == [] for r in data["records"])


def test_to_json_all_failed():
    """A fully failing report has passed false and no passing records."""
    data = json.loads(reporter.to_json(make_failing_report(3)))
    assert data["passed"] is False
    assert data["pass_count"] == 0
    assert data["fail_count"] == 3
    assert not any(r["passed"] for r in data["records"])


def test_to_json_zero_records():
    """An empty report serialises with an empty records list and passed true."""
    data = json.loads(reporter.to_json(validate([])))
    assert data == {
        "passed": True,
        "total": 0,
        "pass_count": 0,
        "fail_count": 0,
        "records": [],
    }


def test_to_json_very_long_failure_message_round_trips():
    """A 100k-character failure message survives a JSON round trip."""
    long_msg = "y" * 100_000
    report = ValidationReport(
        total=1,
        passed=0,
        failed=1,
        results=[RecordResult(record_id="big", passed=False, failures=[long_msg])],
    )
    data = json.loads(reporter.to_json(report))
    assert data["records"][0]["failures"] == [long_msg]


def test_to_json_unicode_is_ascii_escaped_and_round_trips():
    """json.dumps default escapes non-ASCII, and loading restores the original text."""
    report = ValidationReport(
        total=1,
        passed=0,
        failed=1,
        results=[
            RecordResult(
                record_id="日本語",
                passed=False,
                failures=["café \U0001f600"],
            )
        ],
    )
    out = reporter.to_json(report)
    assert out.isascii()
    assert "\\u65e5" in out
    data = json.loads(out)
    assert data["records"][0]["id"] == "日本語"
    assert data["records"][0]["failures"] == ["café \U0001f600"]


def test_to_json_non_serializable_failure_raises_type_error():
    """A failure value json cannot encode makes to_json raise TypeError."""
    report = ValidationReport(
        total=1,
        passed=0,
        failed=1,
        results=[RecordResult(record_id="x", passed=False, failures=[object()])],
    )
    with pytest.raises(TypeError):
        reporter.to_json(report)


def test_to_json_non_serializable_record_id_raises_type_error():
    """A record_id json cannot encode makes to_json raise TypeError."""
    report = ValidationReport(
        total=1,
        passed=0,
        failed=1,
        results=[RecordResult(record_id={1, 2}, passed=False, failures=["f"])],
    )
    with pytest.raises(TypeError):
        reporter.to_json(report)


def test_text_path_tolerates_values_that_break_json():
    """to_text renders the same non-serializable object that makes to_json fail."""
    report = ValidationReport(
        total=1,
        passed=0,
        failed=1,
        results=[RecordResult(record_id="x", passed=False, failures=[object()])],
    )
    assert "Record x:" in reporter.to_text(report)


# ---------------------------------------------------------------- type errors


@pytest.mark.parametrize("func", [reporter.to_text, reporter.to_json])
@pytest.mark.parametrize("bad", [None, 42, "report", {"total": 1}, [], object()])
def test_formatters_reject_non_report_objects(func, bad):
    """to_text and to_json raise AttributeError for objects lacking report attributes."""
    with pytest.raises(AttributeError):
        func(bad)


@pytest.mark.parametrize("fmt", ["text", "json"])
def test_write_rejects_none_report(fmt):
    """write raises AttributeError for a None report in either format."""
    with pytest.raises(AttributeError):
        reporter.write(None, fmt=fmt)


def test_write_none_report_does_not_create_file(tmp_path):
    """A failed formatting step leaves no output file behind."""
    dest = tmp_path / "out.txt"
    with pytest.raises(AttributeError):
        reporter.write(None, dest=str(dest))
    assert not dest.exists()


def test_to_text_report_missing_results_attribute_raises():
    """An object with ok/total/passed/failed but no results fails on a failing report."""

    class Partial:
        ok = False
        total = 1
        passed = 0
        failed = 1

    with pytest.raises(AttributeError):
        reporter.to_text(Partial())


def test_to_text_accepts_duck_typed_report():
    """to_text works with any object exposing the attributes it reads."""

    class Duck:
        ok = True
        total = 0
        passed = 0
        failed = 0
        results = []

    assert reporter.to_text(Duck()).startswith("Validation PASSED")


# ---------------------------------------------------------------- write


def test_write_text_to_file(tmp_path):
    """write with dest and default format saves the text report to the file."""
    report = make_mixed_report()
    dest = tmp_path / "report.txt"
    result = reporter.write(report, dest=str(dest))
    assert result is None
    assert dest.read_text() == reporter.to_text(report)


def test_write_json_to_file(tmp_path):
    """write with fmt='json' and dest saves the JSON report to the file."""
    report = make_mixed_report()
    dest = tmp_path / "report.json"
    reporter.write(report, fmt="json", dest=str(dest))
    assert dest.read_text() == reporter.to_json(report)
    assert json.loads(dest.read_text())["fail_count"] == 2


def test_write_accepts_path_object_dest(tmp_path):
    """write accepts a pathlib.Path as dest because it wraps it in Path()."""
    dest = tmp_path / "p.txt"
    reporter.write(make_passing_report(1), dest=dest)
    assert dest.read_text().startswith("Validation PASSED")


def test_write_file_has_no_trailing_newline(tmp_path):
    """File output is exactly the formatted content, with no added newline."""
    report = make_passing_report(1)
    dest = tmp_path / "r.txt"
    reporter.write(report, dest=str(dest))
    assert dest.read_text() == reporter.to_text(report)
    assert not dest.read_text().endswith("\n")


def test_write_overwrites_existing_file(tmp_path):
    """write replaces the existing content of dest."""
    dest = tmp_path / "r.txt"
    dest.write_text("old content that is much longer than the new report " * 20)
    report = make_passing_report(1)
    reporter.write(report, dest=str(dest))
    assert dest.read_text() == reporter.to_text(report)


def test_write_to_file_prints_nothing_to_stdout(tmp_path, capsys):
    """When dest is given, nothing is printed to stdout."""
    reporter.write(make_mixed_report(), dest=str(tmp_path / "r.txt"))
    assert capsys.readouterr().out == ""


def test_write_text_to_stdout(capsys):
    """write without dest prints the text report plus a newline to stdout."""
    report = make_mixed_report()
    reporter.write(report)
    captured = capsys.readouterr()
    assert captured.out == reporter.to_text(report) + "\n"
    assert captured.err == ""


def test_write_json_to_stdout(capsys):
    """write with fmt='json' and no dest prints the JSON report to stdout."""
    report = make_mixed_report()
    reporter.write(report, fmt="json")
    out = capsys.readouterr().out
    assert out == reporter.to_json(report) + "\n"
    assert json.loads(out)["total"] == 3


def test_write_empty_string_dest_goes_to_stdout(tmp_path, capsys, monkeypatch):
    """An empty-string dest is falsy, so output goes to stdout and no file is made."""
    monkeypatch.chdir(tmp_path)
    reporter.write(make_passing_report(1), dest="")
    assert capsys.readouterr().out.startswith("Validation PASSED")
    assert list(tmp_path.iterdir()) == []


def test_write_zero_records_to_stdout_and_file(tmp_path, capsys):
    """An empty report can be written to both stdout and a file."""
    report = validate([])
    reporter.write(report)
    assert "Total records : 0" in capsys.readouterr().out
    dest = tmp_path / "empty.json"
    reporter.write(report, fmt="json", dest=str(dest))
    assert json.loads(dest.read_text())["records"] == []


def test_write_unicode_json_to_file(tmp_path):
    """JSON output is ASCII-escaped, so unicode ids are written safely to a file."""
    report = ValidationReport(
        total=1,
        passed=0,
        failed=1,
        results=[RecordResult(record_id="日本語", passed=False, failures=["é"])],
    )
    dest = tmp_path / "u.json"
    reporter.write(report, fmt="json", dest=str(dest))
    assert json.loads(dest.read_text())["records"][0]["id"] == "日本語"


def test_write_unicode_text_to_stdout(capsys):
    """Unicode text output reaches stdout intact."""
    report = ValidationReport(
        total=1,
        passed=0,
        failed=1,
        results=[RecordResult(record_id="日本語", passed=False, failures=["é"])],
    )
    reporter.write(report)
    out = capsys.readouterr().out
    assert "  Record 日本語:" in out
    assert "    - é" in out


def test_write_long_message_to_file(tmp_path):
    """A very long failure message is written to a file in full."""
    long_msg = "z" * 200_000
    report = ValidationReport(
        total=1,
        passed=0,
        failed=1,
        results=[RecordResult(record_id="big", passed=False, failures=[long_msg])],
    )
    dest = tmp_path / "big.txt"
    reporter.write(report, dest=str(dest))
    assert long_msg in dest.read_text()


# ---------------------------------------------------------------- exception paths


@pytest.mark.parametrize("fmt", ["xml", "JSON", "Text", "", "yaml"])
def test_write_unknown_format_falls_back_to_text(fmt, capsys):
    """Any fmt other than exactly 'json' (including 'JSON') is treated as text."""
    report = make_mixed_report()
    reporter.write(report, fmt=fmt)
    assert capsys.readouterr().out == reporter.to_text(report) + "\n"


def test_write_unknown_format_falls_back_to_text_in_file(tmp_path):
    """An unsupported format name writes text to the file and raises nothing."""
    report = make_mixed_report()
    dest = tmp_path / "r.out"
    reporter.write(report, fmt="csv", dest=str(dest))
    assert dest.read_text() == reporter.to_text(report)


def test_write_none_format_falls_back_to_text(capsys):
    """fmt=None is not 'json', so write produces text output."""
    reporter.write(make_passing_report(1), fmt=None)
    assert capsys.readouterr().out.startswith("Validation PASSED")


def test_write_missing_parent_directory_raises_file_not_found(tmp_path):
    """write does not create parent directories and raises FileNotFoundError."""
    dest = tmp_path / "no_such_dir" / "r.txt"
    with pytest.raises(FileNotFoundError):
        reporter.write(make_passing_report(1), dest=str(dest))
    assert not dest.parent.exists()


def test_write_dest_is_directory_raises_os_error(tmp_path):
    """Using an existing directory as dest raises an OSError subclass."""
    with pytest.raises(OSError):
        reporter.write(make_passing_report(1), dest=str(tmp_path))


def test_write_parent_is_a_file_raises_os_error(tmp_path):
    """A dest whose parent is a regular file raises an OSError subclass."""
    parent = tmp_path / "afile"
    parent.write_text("x")
    with pytest.raises(OSError):
        reporter.write(make_passing_report(1), dest=str(parent / "r.txt"))


def test_write_json_non_serializable_raises_before_touching_file(tmp_path):
    """JSON serialisation failure in write happens before the file is opened."""
    report = ValidationReport(
        total=1,
        passed=0,
        failed=1,
        results=[RecordResult(record_id="x", passed=False, failures=[object()])],
    )
    dest = tmp_path / "r.json"
    with pytest.raises(TypeError):
        reporter.write(report, fmt="json", dest=str(dest))
    assert not dest.exists()


def test_write_json_non_serializable_prints_nothing(capsys):
    """JSON serialisation failure on the stdout path prints nothing."""
    report = ValidationReport(
        total=1,
        passed=0,
        failed=1,
        results=[RecordResult(record_id="x", passed=False, failures=[object()])],
    )
    with pytest.raises(TypeError):
        reporter.write(report, fmt="json")
    assert capsys.readouterr().out == ""


def test_reporter_source_has_no_explicit_raise():
    """reporter.py contains no raise statements, so errors come only from callees."""
    source = (SMALL_PROJECT_DIR / "reporter.py").read_text()
    assert "raise " not in source


def test_reporter_imports_validation_report_from_validator():
    """reporter exposes the same ValidationReport class that validator defines."""
    assert reporter.ValidationReport is ValidationReport


def test_validate_unknown_rule_error_does_not_reach_reporter():
    """validate raises ValueError for unknown rules, so no report reaches reporter."""
    with pytest.raises(ValueError, match="Unknown rules"):
        validate([{"id": "a"}], rules=["nope"])
