"""Unit tests for the original small_project reporter module."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "sample_jobs" / "small_project")
)

import reporter  # noqa: E402
from validator import RecordResult, ValidationReport  # noqa: E402


def make_report(results):
    passed = sum(1 for r in results if r.passed)
    return ValidationReport(
        total=len(results),
        passed=passed,
        failed=len(results) - passed,
        results=list(results),
    )


@pytest.fixture
def empty_report():
    return make_report([])


@pytest.fixture
def passing_report():
    return make_report([RecordResult("a", True), RecordResult("b", True)])


@pytest.fixture
def failing_report():
    return make_report(
        [
            RecordResult("a", True),
            RecordResult("b", False, ["value negative", "name empty"]),
            RecordResult("c", False, ["missing id"]),
        ]
    )


# _text_lines

def test_text_lines_passing(passing_report):
    assert reporter._text_lines(passing_report) == [
        "Validation PASSED",
        "  Total records : 2",
        "  Passed        : 2",
        "  Failed        : 0",
    ]


def test_text_lines_failing_lists_only_failed_records(failing_report):
    lines = reporter._text_lines(failing_report)
    assert lines[0] == "Validation FAILED"
    assert lines[4:6] == ["", "Failures:"]
    assert lines[6:] == [
        "  Record b:",
        "    - value negative",
        "    - name empty",
        "  Record c:",
        "    - missing id",
    ]
    assert "  Record a:" not in lines


def test_text_lines_empty_report_is_passed(empty_report):
    lines = reporter._text_lines(empty_report)
    assert lines[0] == "Validation PASSED"
    assert lines[1] == "  Total records : 0"
    assert len(lines) == 4


# to_text

def test_to_text_joins_lines_without_trailing_newline(failing_report):
    text = reporter.to_text(failing_report)
    assert text == "\n".join(reporter._text_lines(failing_report))
    assert not text.endswith("\n")


def test_to_text_empty(empty_report):
    assert reporter.to_text(empty_report).startswith("Validation PASSED")


# to_json

def test_to_json_parses_and_has_expected_shape(failing_report):
    data = json.loads(reporter.to_json(failing_report))
    assert data["passed"] is False
    assert data["total"] == 3
    assert data["pass_count"] == 1
    assert data["fail_count"] == 2
    assert data["records"] == [
        {"id": "a", "passed": True, "failures": []},
        {"id": "b", "passed": False, "failures": ["value negative", "name empty"]},
        {"id": "c", "passed": False, "failures": ["missing id"]},
    ]


def test_to_json_empty(empty_report):
    data = json.loads(reporter.to_json(empty_report))
    assert data["passed"] is True
    assert data["total"] == 0
    assert data["records"] == []


def test_to_json_all_passing(passing_report):
    data = json.loads(reporter.to_json(passing_report))
    assert data["passed"] is True
    assert all(r["failures"] == [] for r in data["records"])


def test_to_json_is_indented_with_two_spaces(passing_report):
    assert '\n  "passed": true' in reporter.to_json(passing_report)


# write: stdout

def test_write_default_is_text_to_stdout(failing_report, capsys):
    reporter.write(failing_report)
    out = capsys.readouterr().out
    assert out == reporter.to_text(failing_report) + "\n"


def test_write_json_to_stdout_parses(failing_report, capsys):
    reporter.write(failing_report, fmt="json")
    data = json.loads(capsys.readouterr().out)
    assert data["fail_count"] == 2


def test_write_empty_report_stdout(empty_report, capsys):
    reporter.write(empty_report)
    assert "Total records : 0" in capsys.readouterr().out


def test_write_unknown_format_falls_back_to_text(failing_report, capsys):
    reporter.write(failing_report, fmt="xml")
    out = capsys.readouterr().out
    assert out == reporter.to_text(failing_report) + "\n"
    with pytest.raises(json.JSONDecodeError):
        json.loads(out)


def test_write_empty_dest_goes_to_stdout(passing_report, capsys):
    reporter.write(passing_report, dest="")
    assert "Validation PASSED" in capsys.readouterr().out


# write: files

def test_write_text_file(failing_report, tmp_path, capsys):
    dest = tmp_path / "report.txt"
    reporter.write(failing_report, fmt="text", dest=str(dest))
    assert dest.read_text() == reporter.to_text(failing_report)
    assert capsys.readouterr().out == ""


def test_write_json_file_parses(failing_report, tmp_path):
    dest = tmp_path / "report.json"
    reporter.write(failing_report, fmt="json", dest=str(dest))
    data = json.loads(dest.read_text())
    assert data["total"] == 3


def test_write_file_has_no_trailing_newline(passing_report, tmp_path):
    dest = tmp_path / "report.txt"
    reporter.write(passing_report, dest=str(dest))
    assert not dest.read_text().endswith("\n")


def test_write_unknown_format_to_file_is_text(passing_report, tmp_path):
    dest = tmp_path / "report.out"
    reporter.write(passing_report, fmt="yaml", dest=str(dest))
    assert dest.read_text() == reporter.to_text(passing_report)


def test_write_overwrites_existing_file(passing_report, tmp_path):
    dest = tmp_path / "report.txt"
    dest.write_text("old content that is much longer than the new report " * 20)
    reporter.write(passing_report, dest=str(dest))
    assert dest.read_text() == reporter.to_text(passing_report)


def test_write_missing_parent_dir_raises(passing_report, tmp_path):
    dest = tmp_path / "nope" / "report.txt"
    with pytest.raises(OSError):
        reporter.write(passing_report, dest=str(dest))
