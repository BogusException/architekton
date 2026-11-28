"""Tests for small_project/cli.py."""

import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

SMALL_PROJECT_DIR = (
    Path(__file__).resolve().parent.parent / "sample_jobs" / "small_project"
)
sys.path.insert(0, str(SMALL_PROJECT_DIR))

import pytest  # noqa: E402

import cli  # noqa: E402

HEADER = "id,name,value,timestamp\n"


def run_cli(monkeypatch, *argv):
    """Run cli.main() with the given argv and return the SystemExit code."""
    monkeypatch.setattr(sys, "argv", ["cli.py", *argv])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    return exc.value.code


def plain(text):
    """Strip ANSI colour codes and collapse whitespace (argparse may colour and wrap)."""
    return " ".join(re.sub(r"\x1b\[[0-9;]*m", "", text).split())


def write_csv(tmp_path, body, name="data.csv", header=HEADER):
    path = tmp_path / name
    path.write_text(header + body)
    return path


def write_json(tmp_path, records, name="data.json"):
    path = tmp_path / name
    path.write_text(json.dumps(records))
    return path


# ---------------------------------------------------------------- constants


def test_default_constants():
    """DEFAULT_STEPS and DEFAULT_RULES hold the documented default names."""
    assert cli.DEFAULT_STEPS == ["strip_whitespace", "normalize_value", "add_flag"]
    assert cli.DEFAULT_RULES == ["has_id", "value_non_negative", "name_not_empty"]


# ------------------------------------------------------------- normal cases


def test_csv_success_text_output(tmp_path, monkeypatch, capsys):
    """A valid CSV run exits 0 and prints a PASSED text report to stdout."""
    path = write_csv(tmp_path, "1,alice,10,2024-01-01\n2,bob,20,2024-01-02\n")
    code = run_cli(monkeypatch, str(path))
    out = capsys.readouterr()
    assert code == 0
    assert "Validation PASSED" in out.out
    assert "Total records : 2" in out.out
    assert "Passed        : 2" in out.out
    assert "Failed        : 0" in out.out
    assert out.err == ""


def test_json_input_success(tmp_path, monkeypatch, capsys):
    """A valid JSON array input exits 0 with a PASSED report."""
    path = write_json(
        tmp_path,
        [{"id": "1", "name": "a", "value": 5, "timestamp": "t"}],
    )
    code = run_cli(monkeypatch, str(path))
    out = capsys.readouterr()
    assert code == 0
    assert "Validation PASSED" in out.out
    assert "Total records : 1" in out.out


def test_json_format_output(tmp_path, monkeypatch, capsys):
    """--format json prints a parseable JSON report with the expected keys."""
    path = write_csv(tmp_path, "1,alice,10,t\n")
    code = run_cli(monkeypatch, str(path), "--format", "json")
    data = json.loads(capsys.readouterr().out)
    assert code == 0
    assert data["passed"] is True
    assert data["total"] == 1
    assert data["pass_count"] == 1
    assert data["fail_count"] == 0
    assert data["records"] == [{"id": "1", "passed": True, "failures": []}]


def test_output_file_written_and_stdout_empty(tmp_path, monkeypatch, capsys):
    """--output writes the report to the file and prints nothing to stdout."""
    path = write_csv(tmp_path, "1,alice,10,t\n")
    dest = tmp_path / "report.txt"
    code = run_cli(monkeypatch, str(path), "--output", str(dest))
    out = capsys.readouterr()
    assert code == 0
    assert out.out == ""
    assert "Validation PASSED" in dest.read_text()


def test_output_file_with_json_format(tmp_path, monkeypatch):
    """--format json with --output writes valid JSON into the file."""
    path = write_csv(tmp_path, "1,alice,10,t\n")
    dest = tmp_path / "report.json"
    code = run_cli(monkeypatch, str(path), "--format", "json", "--output", str(dest))
    assert code == 0
    assert json.loads(dest.read_text())["total"] == 1


def test_default_steps_strip_whitespace_makes_blank_name_fail(
    tmp_path, monkeypatch, capsys
):
    """Default steps strip whitespace, so a whitespace-only name fails name_not_empty."""
    path = write_csv(tmp_path, "1,   ,10,t\n")
    code = run_cli(monkeypatch, str(path))
    out = capsys.readouterr().out
    assert code == 1
    assert "Validation FAILED" in out
    assert "name_not_empty: missing or empty 'name'" in out


def test_explicit_steps_and_rules(tmp_path, monkeypatch, capsys):
    """Explicit --steps and --rules values are accepted and used."""
    path = write_csv(tmp_path, "1,alice,10,t\n")
    code = run_cli(
        monkeypatch,
        str(path),
        "--steps", "strip_whitespace", "normalize_value",
        "--rules", "has_id",
    )
    assert code == 0
    assert "Validation PASSED" in capsys.readouterr().out


def test_negative_value_fails_with_exit_1(tmp_path, monkeypatch, capsys):
    """A record with a negative value gives a FAILED report and exit code 1."""
    path = write_csv(tmp_path, "1,alice,-5,t\n2,bob,3,t\n")
    code = run_cli(monkeypatch, str(path))
    out = capsys.readouterr().out
    assert code == 1
    assert "Validation FAILED" in out
    assert "Passed        : 1" in out
    assert "Failed        : 1" in out
    assert "Record 1:" in out
    assert "value_non_negative: 'value' is negative: -5.0" in out


def test_missing_id_fails_with_exit_1(tmp_path, monkeypatch, capsys):
    """An empty id field fails has_id and exits 1."""
    path = write_csv(tmp_path, ",alice,10,t\n")
    code = run_cli(monkeypatch, str(path))
    assert code == 1
    assert "has_id: missing or empty 'id'" in capsys.readouterr().out


def test_failed_json_report_has_failures(tmp_path, monkeypatch, capsys):
    """A failing run with --format json lists the failure strings and exits 1."""
    path = write_csv(tmp_path, "1,alice,-1,t\n")
    code = run_cli(monkeypatch, str(path), "--format", "json")
    data = json.loads(capsys.readouterr().out)
    assert code == 1
    assert data["passed"] is False
    assert data["fail_count"] == 1
    assert data["records"][0]["failures"] == [
        "value_non_negative: 'value' is negative: -1.0"
    ]


def test_json_null_value_normalised_to_zero(tmp_path, monkeypatch):
    """A null value is turned into 0.0 by normalize_value, so the run passes."""
    path = write_json(
        tmp_path,
        [{"id": "1", "name": "a", "value": None, "timestamp": "t"}],
    )
    assert run_cli(monkeypatch, str(path)) == 0


# --------------------------------------------------------------- boundaries


def test_steps_flag_with_no_values_skips_transformations(
    tmp_path, monkeypatch, capsys
):
    """--steps with no values applies no steps, so padded names are not stripped."""
    path = write_csv(tmp_path, "1,   ,10,t\n")
    code = run_cli(monkeypatch, str(path), "--steps", "--rules", "has_id")
    assert code == 0
    assert "Validation PASSED" in capsys.readouterr().out


def test_steps_empty_leaves_non_numeric_value_to_fail(
    tmp_path, monkeypatch, capsys
):
    """With --steps empty, 'abc' is not normalised and fails value_non_negative."""
    path = write_csv(tmp_path, "1,alice,abc,t\n")
    code = run_cli(monkeypatch, str(path), "--steps")
    assert code == 1
    assert "'value' is not numeric: 'abc'" in capsys.readouterr().out


def test_rules_flag_with_no_values_runs_all_registered_rules(
    tmp_path, monkeypatch, capsys
):
    """--rules with no values makes validate() fall back to every registered rule."""
    path = write_csv(tmp_path, "1,alice,-5,t\n")
    code = run_cli(monkeypatch, str(path), "--rules")
    assert code == 1
    assert "value_non_negative" in capsys.readouterr().out


def test_csv_with_header_only_passes_with_zero_records(
    tmp_path, monkeypatch, capsys
):
    """A CSV with only the header row yields zero records and exit 0."""
    path = write_csv(tmp_path, "")
    code = run_cli(monkeypatch, str(path))
    out = capsys.readouterr().out
    assert code == 0
    assert "Total records : 0" in out
    assert "Validation PASSED" in out


def test_completely_empty_csv_reports_missing_columns(
    tmp_path, monkeypatch, capsys
):
    """A zero-byte CSV has no header, so it exits 2 with the missing-columns error."""
    path = tmp_path / "empty.csv"
    path.write_text("")
    code = run_cli(monkeypatch, str(path))
    err = capsys.readouterr().err
    assert code == 2
    assert err.startswith("error: CSV missing required columns:")
    assert "'id'" in err


def test_empty_json_array_passes(tmp_path, monkeypatch, capsys):
    """An empty JSON array yields zero records and exit 0."""
    path = write_json(tmp_path, [])
    code = run_cli(monkeypatch, str(path))
    assert code == 0
    assert "Total records : 0" in capsys.readouterr().out


def test_zero_byte_json_file_exits_2(tmp_path, monkeypatch, capsys):
    """A zero-byte JSON file raises JSONDecodeError (a ValueError), so exit 2."""
    path = tmp_path / "empty.json"
    path.write_text("")
    code = run_cli(monkeypatch, str(path))
    err = capsys.readouterr().err
    assert code == 2
    assert err.startswith("error: ")
    assert "Expecting value" in err


def test_optional_arguments_default_values(monkeypatch):
    """Without optional flags, collaborators get the default steps, rules, fmt and dest."""
    calls = {}
    report = SimpleNamespace(ok=True)
    monkeypatch.setattr(cli, "load", lambda p: [{"id": "1"}])
    monkeypatch.setattr(
        cli, "apply", lambda recs, steps: calls.setdefault("steps", steps) and recs
    )
    monkeypatch.setattr(
        cli, "validate", lambda recs, rules: calls.setdefault("rules", rules) and report
    )

    def fake_write(rep, fmt, dest):
        calls["fmt"] = fmt
        calls["dest"] = dest

    monkeypatch.setattr(cli, "write", fake_write)
    assert run_cli(monkeypatch, "whatever.csv") == 0
    assert calls["steps"] == cli.DEFAULT_STEPS
    assert calls["rules"] == cli.DEFAULT_RULES
    assert calls["fmt"] == "text"
    assert calls["dest"] is None


def test_main_passes_parsed_arguments_to_collaborators(monkeypatch):
    """main() forwards file, steps, rules, format and output to the collaborators."""
    seen = {}
    report = SimpleNamespace(ok=True)

    def fake_load(path):
        seen["path"] = path
        return ["rec"]

    def fake_apply(records, steps):
        seen["apply"] = (records, steps)
        return ["rec2"]

    def fake_validate(records, rules):
        seen["validate"] = (records, rules)
        return report

    def fake_write(rep, fmt, dest):
        seen["write"] = (rep, fmt, dest)

    monkeypatch.setattr(cli, "load", fake_load)
    monkeypatch.setattr(cli, "apply", fake_apply)
    monkeypatch.setattr(cli, "validate", fake_validate)
    monkeypatch.setattr(cli, "write", fake_write)

    code = run_cli(
        monkeypatch, "in.json", "--steps", "a", "b", "--rules", "r1",
        "--format", "json", "--output", "out.txt",
    )
    assert code == 0
    assert seen["path"] == "in.json"
    assert seen["apply"] == (["rec"], ["a", "b"])
    assert seen["validate"] == (["rec2"], ["r1"])
    assert seen["write"] == (report, "json", "out.txt")


# -------------------------------------------------------------- exit codes


def test_exit_code_0_when_report_ok_stubbed(monkeypatch):
    """A report with ok=True makes main() exit 0 (stubbed collaborators)."""
    monkeypatch.setattr(cli, "load", lambda p: [])
    monkeypatch.setattr(cli, "apply", lambda r, s: r)
    monkeypatch.setattr(cli, "validate", lambda r, rules: SimpleNamespace(ok=True))
    monkeypatch.setattr(cli, "write", lambda rep, fmt, dest: None)
    assert run_cli(monkeypatch, "x.csv") == 0


def test_exit_code_1_when_report_not_ok_stubbed(monkeypatch):
    """A report with ok=False makes main() exit 1 (stubbed collaborators)."""
    monkeypatch.setattr(cli, "load", lambda p: [])
    monkeypatch.setattr(cli, "apply", lambda r, s: r)
    monkeypatch.setattr(cli, "validate", lambda r, rules: SimpleNamespace(ok=False))
    monkeypatch.setattr(cli, "write", lambda rep, fmt, dest: None)
    assert run_cli(monkeypatch, "x.csv") == 1


def test_write_runs_before_exit_even_when_report_fails(monkeypatch):
    """The report is written before the exit code 1 is raised."""
    written = []
    monkeypatch.setattr(cli, "load", lambda p: [])
    monkeypatch.setattr(cli, "apply", lambda r, s: r)
    monkeypatch.setattr(cli, "validate", lambda r, rules: SimpleNamespace(ok=False))
    monkeypatch.setattr(cli, "write", lambda rep, fmt, dest: written.append(rep))
    assert run_cli(monkeypatch, "x.csv") == 1
    assert len(written) == 1


# ----------------------------------------------------- error handler (exit 2)


def test_missing_input_file_exits_2(tmp_path, monkeypatch, capsys):
    """A nonexistent .csv path hits the FileNotFoundError handler: stderr message, exit 2."""
    code = run_cli(monkeypatch, str(tmp_path / "nope.csv"))
    out = capsys.readouterr()
    assert code == 2
    assert out.err.startswith("error: ")
    assert "No such file or directory" in out.err
    assert out.out == ""


def test_missing_json_file_exits_2(tmp_path, monkeypatch, capsys):
    """A nonexistent .json path also exits 2 with an error on stderr."""
    code = run_cli(monkeypatch, str(tmp_path / "nope.json"))
    assert code == 2
    assert capsys.readouterr().err.startswith("error: ")


def test_unsupported_extension_exits_2(tmp_path, monkeypatch, capsys):
    """An unsupported file extension raises ValueError and exits 2."""
    path = tmp_path / "data.txt"
    path.write_text("x")
    code = run_cli(monkeypatch, str(path))
    assert code == 2
    assert capsys.readouterr().err == "error: Unsupported file type: .txt\n"


def test_no_extension_exits_2(tmp_path, monkeypatch, capsys):
    """A file with no extension reports an empty unsupported suffix and exits 2."""
    path = tmp_path / "data"
    path.write_text("x")
    code = run_cli(monkeypatch, str(path))
    assert code == 2
    assert capsys.readouterr().err == "error: Unsupported file type: \n"


def test_csv_missing_required_columns_exits_2(tmp_path, monkeypatch, capsys):
    """A CSV lacking required columns exits 2 and lists the missing ones sorted."""
    path = tmp_path / "bad.csv"
    path.write_text("id,name\n1,a\n")
    code = run_cli(monkeypatch, str(path))
    assert code == 2
    assert capsys.readouterr().err == (
        "error: CSV missing required columns: ['timestamp', 'value']\n"
    )


def test_json_object_instead_of_array_exits_2(tmp_path, monkeypatch, capsys):
    """A JSON object (not an array) exits 2 with the expected-array message."""
    path = tmp_path / "obj.json"
    path.write_text('{"id": 1}')
    code = run_cli(monkeypatch, str(path))
    assert code == 2
    assert capsys.readouterr().err == "error: Expected a JSON array, got dict\n"


def test_malformed_json_exits_2(tmp_path, monkeypatch, capsys):
    """Malformed JSON raises JSONDecodeError (a ValueError) and exits 2."""
    path = tmp_path / "bad.json"
    path.write_text("[1, 2")
    code = run_cli(monkeypatch, str(path))
    assert code == 2
    assert capsys.readouterr().err.startswith("error: ")


def test_unknown_step_exits_2(tmp_path, monkeypatch, capsys):
    """An unknown transformation name exits 2 with the unknown-steps message."""
    path = write_csv(tmp_path, "1,a,1,t\n")
    code = run_cli(monkeypatch, str(path), "--steps", "bogus")
    assert code == 2
    assert capsys.readouterr().err == "error: Unknown transformations: ['bogus']\n"


def test_unknown_rule_exits_2(tmp_path, monkeypatch, capsys):
    """An unknown rule name exits 2 with the unknown-rules message."""
    path = write_csv(tmp_path, "1,a,1,t\n")
    code = run_cli(monkeypatch, str(path), "--rules", "nope")
    assert code == 2
    assert capsys.readouterr().err == "error: Unknown rules: ['nope']\n"


def test_add_flag_on_non_numeric_value_exits_2(tmp_path, monkeypatch, capsys):
    """add_flag alone on a non-numeric value raises ValueError, which maps to exit 2."""
    path = write_csv(tmp_path, "1,a,abc,t\n")
    code = run_cli(monkeypatch, str(path), "--steps", "add_flag")
    assert code == 2
    assert "could not convert string to float" in capsys.readouterr().err


def test_valueerror_from_stubbed_collaborator_exits_2(monkeypatch, capsys):
    """A ValueError raised by any stubbed collaborator is printed and exits 2."""

    def boom(path):
        raise ValueError("custom failure")

    monkeypatch.setattr(cli, "load", boom)
    code = run_cli(monkeypatch, "x.csv")
    out = capsys.readouterr()
    assert code == 2
    assert out.err == "error: custom failure\n"
    assert out.out == ""


def test_filenotfound_from_stubbed_write_exits_2(monkeypatch, capsys):
    """A FileNotFoundError raised by write (for example a bad --output dir) exits 2."""
    monkeypatch.setattr(cli, "load", lambda p: [])
    monkeypatch.setattr(cli, "apply", lambda r, s: r)
    monkeypatch.setattr(cli, "validate", lambda r, rules: SimpleNamespace(ok=True))

    def bad_write(rep, fmt, dest):
        raise FileNotFoundError("no such dir")

    monkeypatch.setattr(cli, "write", bad_write)
    code = run_cli(monkeypatch, "x.csv", "--output", "/missing/dir/out.txt")
    assert code == 2
    assert capsys.readouterr().err == "error: no such dir\n"


def test_output_to_missing_directory_exits_2(tmp_path, monkeypatch, capsys):
    """Writing the report into a nonexistent directory exits 2 via FileNotFoundError."""
    path = write_csv(tmp_path, "1,a,1,t\n")
    dest = tmp_path / "missing_dir" / "out.txt"
    code = run_cli(monkeypatch, str(path), "--output", str(dest))
    assert code == 2
    assert capsys.readouterr().err.startswith("error: ")


def test_unhandled_exception_type_propagates(monkeypatch):
    """Exceptions other than ValueError/FileNotFoundError are not caught by main()."""

    def boom(path):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(cli, "load", boom)
    monkeypatch.setattr(sys, "argv", ["cli.py", "x.csv"])
    with pytest.raises(RuntimeError, match="unexpected"):
        cli.main()


# ------------------------------------------------------ argparse SystemExit


def test_missing_positional_argument_exits_2(monkeypatch, capsys):
    """Omitting the file argument makes argparse exit 2 with a usage error on stderr."""
    code = run_cli(monkeypatch)
    err = capsys.readouterr().err
    assert code == 2
    assert "usage:" in err
    assert "the following arguments are required: file" in err


def test_invalid_format_choice_exits_2(monkeypatch, capsys):
    """An invalid --format value makes argparse exit 2 and name the bad choice."""
    code = run_cli(monkeypatch, "x.csv", "--format", "xml")
    err = capsys.readouterr().err
    assert code == 2
    assert "invalid choice: 'xml'" in err


def test_unknown_option_exits_2(monkeypatch, capsys):
    """An unrecognised option makes argparse exit 2."""
    code = run_cli(monkeypatch, "x.csv", "--bogus")
    assert code == 2
    assert "unrecognized arguments: --bogus" in capsys.readouterr().err


def test_format_without_value_exits_2(monkeypatch, capsys):
    """--format with no value makes argparse exit 2 with an 'expected one argument' error."""
    code = run_cli(monkeypatch, "x.csv", "--format")
    assert code == 2
    assert "expected one argument" in capsys.readouterr().err


def test_output_without_value_exits_2(monkeypatch, capsys):
    """--output with no value makes argparse exit 2 with an 'expected one argument' error."""
    code = run_cli(monkeypatch, "x.csv", "--output")
    assert code == 2
    assert "expected one argument" in capsys.readouterr().err


def test_help_exits_0_and_shows_defaults(monkeypatch, capsys):
    """--help prints usage with the default steps and rules to stdout and exits 0."""
    code = run_cli(monkeypatch, "--help")
    out = plain(capsys.readouterr().out)
    assert code == 0
    assert "usage:" in out
    assert "(default: strip_whitespace normalize_value add_flag)" in out
    assert "(default: has_id value_non_negative name_not_empty)" in out


def test_argparse_errors_do_not_use_cli_error_prefix(monkeypatch, capsys):
    """argparse errors are reported by argparse itself, not by the 'error:' handler in main()."""
    run_cli(monkeypatch, "x.csv", "--format", "xml")
    err = plain(capsys.readouterr().err)
    assert ": error: argument --format: invalid choice: 'xml'" in err
    assert not err.startswith("error: ")


# -------------------------------------------------------------- type errors


def test_main_rejects_positional_arguments():
    """main() takes no parameters, so passing a value raises TypeError."""
    with pytest.raises(TypeError):
        cli.main("data.csv")


def test_main_rejects_keyword_arguments():
    """main() takes no parameters, so passing a keyword raises TypeError."""
    with pytest.raises(TypeError):
        cli.main(file="data.csv")


def test_json_records_that_are_not_dicts_raise_attribute_error(
    tmp_path, monkeypatch
):
    """Non-dict JSON records break strip_whitespace with AttributeError, which main() does not catch."""
    path = tmp_path / "ints.json"
    path.write_text("[1, 2, 3]")
    monkeypatch.setattr(sys, "argv", ["cli.py", str(path)])
    with pytest.raises(AttributeError):
        cli.main()


def test_non_dict_json_records_pass_when_no_steps_but_fail_validation(
    tmp_path, monkeypatch
):
    """With --steps empty, non-dict records reach validate and raise AttributeError there."""
    path = tmp_path / "ints.json"
    path.write_text("[1]")
    monkeypatch.setattr(sys, "argv", ["cli.py", str(path), "--steps"])
    with pytest.raises(AttributeError):
        cli.main()


def test_sys_argv_non_string_entry_raises_type_error(monkeypatch):
    """A non-string entry in sys.argv makes argparse raise TypeError (not caught by main())."""
    monkeypatch.setattr(sys, "argv", ["cli.py", 123])
    with pytest.raises((TypeError, AttributeError)):
        cli.main()
