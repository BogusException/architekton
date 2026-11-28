"""Unit tests for small_project/cli.py (original module behavior)."""

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent / "sample_jobs" / "small_project"),
)

import cli  # noqa: E402
from validator import RecordResult, ValidationReport  # noqa: E402


CSV_GOOD = "id,name,value,timestamp\n1,alpha,10,2026-01-01\n2,beta,150,2026-01-02\n"
CSV_BAD = "id,name,value,timestamp\n1,alpha,-5,2026-01-01\n,beta,10,2026-01-02\n"


def run_cli(monkeypatch, *argv):
    """Invoke cli.main() with argv and return the SystemExit code."""
    monkeypatch.setattr(sys, "argv", ["cli.py", *argv])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    return exc.value.code


@pytest.fixture
def good_csv(tmp_path):
    p = tmp_path / "good.csv"
    p.write_text(CSV_GOOD)
    return p


@pytest.fixture
def bad_csv(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text(CSV_BAD)
    return p


def test_defaults_constants():
    assert cli.DEFAULT_STEPS == ["strip_whitespace", "normalize_value", "add_flag"]
    assert cli.DEFAULT_RULES == ["has_id", "value_non_negative", "name_not_empty"]


# ---- normal paths ----

def test_valid_csv_text_report_exit_0(monkeypatch, capsys, good_csv):
    code = run_cli(monkeypatch, str(good_csv))
    out = capsys.readouterr().out
    assert code == 0
    assert "Validation PASSED" in out
    assert "Total records : 2" in out


def test_valid_json_input_exit_0(monkeypatch, capsys, tmp_path):
    p = tmp_path / "data.json"
    p.write_text(json.dumps([{"id": "1", "name": "a", "value": 5, "timestamp": "t"}]))
    assert run_cli(monkeypatch, str(p)) == 0
    assert "PASSED" in capsys.readouterr().out


def test_json_format_output(monkeypatch, capsys, good_csv):
    code = run_cli(monkeypatch, str(good_csv), "--format", "json")
    data = json.loads(capsys.readouterr().out)
    assert code == 0
    assert data["passed"] is True
    assert data["total"] == 2
    assert data["pass_count"] == 2


def test_output_file_written_not_stdout(monkeypatch, capsys, good_csv, tmp_path):
    dest = tmp_path / "report.txt"
    code = run_cli(monkeypatch, str(good_csv), "--output", str(dest))
    assert code == 0
    assert capsys.readouterr().out == ""
    assert "Validation PASSED" in dest.read_text()


def test_failing_records_exit_1_and_listed(monkeypatch, capsys, bad_csv):
    code = run_cli(monkeypatch, str(bad_csv))
    out = capsys.readouterr().out
    assert code == 1
    assert "Validation FAILED" in out
    assert "value_non_negative" in out
    assert "has_id" in out


def test_custom_steps_and_rules_passed_through(monkeypatch, good_csv):
    fake_report = mock.Mock(ok=True)
    with mock.patch.object(cli, "load", return_value=[{"id": 1}]) as m_load, \
         mock.patch.object(cli, "apply", return_value=[{"id": 1}]) as m_apply, \
         mock.patch.object(cli, "validate", return_value=fake_report) as m_val, \
         mock.patch.object(cli, "write") as m_write:
        code = run_cli(
            monkeypatch, str(good_csv),
            "--steps", "strip_whitespace",
            "--rules", "has_id", "name_not_empty",
            "--format", "json", "--output", "out.json",
        )
    assert code == 0
    m_load.assert_called_once_with(str(good_csv))
    m_apply.assert_called_once_with([{"id": 1}], ["strip_whitespace"])
    m_val.assert_called_once_with([{"id": 1}], ["has_id", "name_not_empty"])
    m_write.assert_called_once_with(fake_report, fmt="json", dest="out.json")


def test_defaults_used_when_flags_absent(monkeypatch):
    fake_report = mock.Mock(ok=True)
    with mock.patch.object(cli, "load", return_value=[]), \
         mock.patch.object(cli, "apply", return_value=[]) as m_apply, \
         mock.patch.object(cli, "validate", return_value=fake_report) as m_val, \
         mock.patch.object(cli, "write") as m_write:
        run_cli(monkeypatch, "whatever.csv")
    m_apply.assert_called_once_with([], cli.DEFAULT_STEPS)
    m_val.assert_called_once_with([], cli.DEFAULT_RULES)
    m_write.assert_called_once_with(fake_report, fmt="text", dest=None)


def test_exit_code_follows_report_ok(monkeypatch):
    report = ValidationReport(
        total=1, passed=0, failed=1,
        results=[RecordResult("1", False, ["x"])],
    )
    with mock.patch.object(cli, "load", return_value=[]), \
         mock.patch.object(cli, "apply", return_value=[]), \
         mock.patch.object(cli, "validate", return_value=report), \
         mock.patch.object(cli, "write"):
        assert run_cli(monkeypatch, "f.csv") == 1


def test_empty_csv_with_headers_passes(monkeypatch, capsys, tmp_path):
    p = tmp_path / "empty.csv"
    p.write_text("id,name,value,timestamp\n")
    assert run_cli(monkeypatch, str(p)) == 0
    assert "Total records : 0" in capsys.readouterr().out


# ---- error paths (exit 2) ----

def test_missing_file_exit_2(monkeypatch, capsys, tmp_path):
    code = run_cli(monkeypatch, str(tmp_path / "nope.csv"))
    err = capsys.readouterr().err
    assert code == 2
    assert err.startswith("error:")


def test_unsupported_extension_exit_2(monkeypatch, capsys, tmp_path):
    p = tmp_path / "data.txt"
    p.write_text("hi")
    assert run_cli(monkeypatch, str(p)) == 2
    assert "Unsupported file type" in capsys.readouterr().err


def test_csv_missing_columns_exit_2(monkeypatch, capsys, tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("id,name\n1,a\n")
    assert run_cli(monkeypatch, str(p)) == 2
    assert "missing required columns" in capsys.readouterr().err


def test_json_not_array_exit_2(monkeypatch, capsys, tmp_path):
    p = tmp_path / "x.json"
    p.write_text('{"id": 1}')
    assert run_cli(monkeypatch, str(p)) == 2
    assert "Expected a JSON array" in capsys.readouterr().err


def test_malformed_json_exit_2(monkeypatch, capsys, tmp_path):
    p = tmp_path / "x.json"
    p.write_text("{not json")
    assert run_cli(monkeypatch, str(p)) == 2
    assert capsys.readouterr().err.startswith("error:")


def test_unknown_step_exit_2(monkeypatch, capsys, good_csv):
    assert run_cli(monkeypatch, str(good_csv), "--steps", "bogus") == 2
    assert "Unknown transformations" in capsys.readouterr().err


def test_unknown_rule_exit_2(monkeypatch, capsys, good_csv):
    assert run_cli(monkeypatch, str(good_csv), "--rules", "bogus") == 2
    assert "Unknown rules" in capsys.readouterr().err


def test_error_message_goes_to_stderr_only(monkeypatch, capsys, tmp_path):
    run_cli(monkeypatch, str(tmp_path / "nope.csv"))
    assert capsys.readouterr().out == ""


# ---- argparse behavior ----

def test_no_args_argparse_exit_2(monkeypatch, capsys):
    assert run_cli(monkeypatch) == 2
    assert "usage" in capsys.readouterr().err.lower()


def test_invalid_format_choice_exit_2(monkeypatch, capsys, good_csv):
    assert run_cli(monkeypatch, str(good_csv), "--format", "xml") == 2
    assert "invalid choice" in capsys.readouterr().err


def test_help_exit_0(monkeypatch, capsys):
    assert run_cli(monkeypatch, "--help") == 0
    assert "--steps" in capsys.readouterr().out


# ---- edge cases / suspected source bugs ----

def test_steps_flag_without_values_applies_no_steps(monkeypatch):
    fake_report = mock.Mock(ok=True)
    with mock.patch.object(cli, "load", return_value=[{"id": 1}]), \
         mock.patch.object(cli, "apply", return_value=[{"id": 1}]) as m_apply, \
         mock.patch.object(cli, "validate", return_value=fake_report), \
         mock.patch.object(cli, "write"):
        run_cli(monkeypatch, "f.csv", "--steps")
    m_apply.assert_called_once_with([{"id": 1}], [])


@pytest.mark.xfail(
    reason="bug: bare '--rules' passes [] to validate(), whose 'rules or list(_RULES)' "
           "runs ALL rules instead of none",
    strict=True,
)
def test_empty_rules_runs_no_rules(monkeypatch, tmp_path):
    p = tmp_path / "neg.csv"
    p.write_text("id,name,value,timestamp\n1,a,-5,t\n")
    # With no rules selected, a negative value should not fail validation.
    assert run_cli(monkeypatch, str(p), "--rules") == 0


@pytest.mark.xfail(
    reason="bug: load_json does not check record types, so non-dict records raise "
           "an uncaught AttributeError (traceback) instead of a clean exit 2",
    strict=True,
)
def test_json_array_of_non_dicts_exit_2(monkeypatch, tmp_path):
    p = tmp_path / "x.json"
    p.write_text("[1, 2, 3]")
    assert run_cli(monkeypatch, str(p)) == 2


@pytest.mark.xfail(
    reason="bug: only ValueError and FileNotFoundError are caught, so other OSErrors "
           "(e.g. IsADirectoryError, PermissionError) escape as tracebacks",
    strict=True,
)
def test_directory_named_csv_exit_2(monkeypatch, tmp_path):
    d = tmp_path / "dir.csv"
    d.mkdir()
    assert run_cli(monkeypatch, str(d)) == 2


@pytest.mark.xfail(
    reason="bug: CSV opened without encoding handling, so a UTF-8 BOM corrupts the "
           "'id' header and raises 'missing required columns'",
    strict=True,
)
def test_csv_with_utf8_bom_loads(monkeypatch, tmp_path):
    p = tmp_path / "bom.csv"
    p.write_bytes(b"\xef\xbb\xbf" + CSV_GOOD.encode("utf-8"))
    assert run_cli(monkeypatch, str(p)) == 0
