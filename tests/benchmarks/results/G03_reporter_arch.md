# reporter.py architecture overview

reporter.py turns a `ValidationReport` from validator.py into plain text or JSON and sends it to stdout or a file.

Line numbers refer to `tests/benchmarks/sample_jobs/small_project/reporter.py` unless another file is named.

## Design patterns

1. Separation of formatting from output. `to_text` (lines 31-32) and `to_json` (lines 35-50) only build and return a string. They do no I/O. `write` (lines 53-59) is the only function that touches stdout or the filesystem. This lets a caller or a test get the rendered string without printing or writing anything.

2. Formatter selection by name. `write` picks a formatter from the `fmt` string with a conditional expression at line 55: `to_json(report) if fmt == "json" else to_text(report)`. This is a two-way branch, not a registry. There is no dict of formatters, so adding a third format means editing line 55.

3. Default-to-text fallback. Any `fmt` that is not exactly `"json"` is rendered as text (line 55). There is no validation of `fmt` inside reporter.py. The only guard is `choices=["text", "json"]` in the CLI parser (cli.py, line 41).

4. Private helper for line assembly. `_text_lines` (lines 13-28) builds a `list[str]`. `to_text` joins it with newlines (line 32). The helper keeps the line logic apart from the join, so the same lines could feed a different renderer.

5. Summary first, detail on failure. `_text_lines` always emits the four summary lines (lines 14-19). It adds the "Failures:" block only when `report.ok` is false (lines 20-27), and inside that block it lists only results where `result.passed` is false (line 24).

6. Projection to a plain dict. `to_json` copies selected fields into a new dict (lines 36-49) before `json.dumps(data, indent=2)` (line 50). The JSON schema is therefore defined by this function, not by the dataclasses. It renames fields: `report.ok` becomes `"passed"`, `report.passed` becomes `"pass_count"`, `report.failed` becomes `"fail_count"`, and `r.record_id` becomes `"id"`.

7. Optional destination. `write` treats `dest=None` as "use stdout" (lines 56-59). The check is a truthiness test, so an empty string also goes to stdout.

## Data flow

Input is a `ValidationReport` dataclass (validator.py, lines 55-60). It holds `total: int`, `passed: int`, `failed: int`, and `results: list[RecordResult]`. It also has an `ok` property (validator.py, lines 62-64) that returns `failed == 0`. Each `RecordResult` (validator.py, lines 48-52) holds `record_id: str`, `passed: bool`, and `failures: list[str]`.

1. cli.py `main` calls `write(report, fmt=args.format, dest=args.output)` (cli.py, line 57). `args.format` is a `str`, either `"text"` or `"json"`. `args.output` is `str | None`.
2. `write` (line 53) receives `(ValidationReport, str, str | None)` and picks a formatter at line 55.
3. Text path: `to_text` (line 31) calls `_text_lines` (line 13), which returns `list[str]`. `to_text` joins it with `"\n"` and returns a `str`. The string has no trailing newline.
4. JSON path: `to_json` (line 35) builds a `dict` with a `list[dict]` under `"records"`, then `json.dumps(..., indent=2)` returns a `str`.
5. Output: if `dest` is truthy, `Path(dest).write_text(content)` writes the string with no trailing newline (line 57). Otherwise `print(content, file=sys.stdout)` writes it with a trailing newline (line 59). `write` returns `None`.
6. Control returns to cli.py, which exits with code 0 if `report.ok` and 1 if not (cli.py, line 58).

Unknown format: `write` does not raise. Any `fmt` other than the exact string `"json"` (including `"JSON"`, `"csv"`, or `""`) produces the text output (line 55). From the CLI this cannot happen, because argparse rejects other values first.

Empty input: a report with zero records has `total=0`, `passed=0`, `failed=0`, `results=[]`, so `ok` is true. Text output is the "Validation PASSED" line plus three zero counters, with no "Failures:" block. JSON output has `"passed": true`, all counts at 0, and `"records": []`. No exception occurs. Note that `validate` (validator.py, line 67) returns this same shape for an empty record list, so "no data" and "all records passed" cannot be told apart in the output.

Error behavior: reporter.py has no try/except. If `dest` points into a missing directory, `write_text` raises `FileNotFoundError`, which cli.py catches and maps to exit code 2 (cli.py, lines 59-61). A `PermissionError` or other `OSError` is not caught and ends in a traceback.

## External dependencies

Imports in reporter.py:

| Line | Import | Use |
| --- | --- | --- |
| 6 | `json` | `json.dumps` in `to_json` (line 50) |
| 7 | `sys` | `sys.stdout` as the print target in `write` (line 59) |
| 8 | `pathlib.Path` | `Path(dest).write_text` in `write` (line 57) |
| 10 | `validator.ValidationReport` | Type annotation on all three formatter and writer functions. It is not used at runtime. |

All imports except `validator` are standard library. The `from validator import ...` form is a flat, top-level import, so it works only when the small_project directory is on `sys.path` (for example when cli.py runs as a script from that directory).

Producers of its input: validator.py. `validate` (validator.py, lines 67-93) builds the `ValidationReport` and its `RecordResult` list. cli.py does not construct the report itself. It passes along what `validate` returns (cli.py, line 56).

Callers: cli.py only. It imports `write` at line 13 and calls it at line 57. The other sibling modules (data_loader.py, transformer.py) do not import reporter.py. Nothing outside cli.py calls `to_text` or `to_json` directly.

## Extending or replacing

Steps to add a new output format (CSV as the example):

1. Add a function in reporter.py, for example `to_csv(report: ValidationReport) -> str`. Keep it free of I/O, like `to_text` and `to_json`. Use `csv.writer` over an `io.StringIO` and write one row per `report.results` entry (`record_id`, `passed`, and the failures joined into one cell). Add `import csv` and `import io` to the import block at lines 6-8.
2. Change the selection at line 55 of `write`. For two or more extra formats, replace the conditional with a dict such as `_FORMATTERS = {"text": to_text, "json": to_json, "csv": to_csv}` and look up `fmt`. Raise `ValueError` on an unknown key, so a typo no longer falls back to text. cli.py already maps `ValueError` to exit code 2 (cli.py, line 59).
3. Add `"csv"` to `choices` in the `--format` argument (cli.py, line 41). Without this step the new format cannot be reached from the command line.
4. Add tests for the new formatter on three inputs: a passing report, a failing report, and an empty report (`total=0`).

For HTML, the steps are the same. Use `html.escape` on every `record_id` and failure message, because they come from user data files.

Input contract for a replacement reporter. It must accept a `ValidationReport` and read only these attributes:

- `report.ok` (`bool`, property), `report.total`, `report.passed`, `report.failed` (all `int`)
- `report.results`, an iterable of `RecordResult`
- on each result: `record_id` (`str`), `passed` (`bool`), `failures` (`list[str]`)

If the replacement is called from cli.py, it must also expose `write(report, fmt=..., dest=...)` with the same keyword names. It should return `None`, because cli.py ignores the return value.

Coupling points that would break:

1. Field names in validator.py. `_text_lines` and `to_json` read `report.ok`, `report.total`, `report.passed`, `report.failed`, `report.results`, `result.record_id`, `result.passed`, and `result.failures` (lines 15-19, 23-26, 37-47). Renaming any of them in validator.py raises `AttributeError` at report time.
2. The `passed` name clash. `report.passed` is an `int` count and `result.passed` is a `bool`. Swapping or retyping either one gives wrong output with no error, for example a bool where a count is expected.
3. The `ok` property. If `ok` stops being derived from `failed == 0`, the text header (line 15), the failures block (line 20), the JSON `"passed"` key (line 37), and the CLI exit code (cli.py, line 58) all change together.
4. The `write` signature. cli.py calls it with keyword arguments `fmt` and `dest` (cli.py, line 57). Renaming either parameter breaks the call.
5. The format list in cli.py. The `choices` list (cli.py, line 41) and the branch at line 55 of reporter.py must be kept in step by hand. Nothing checks that they agree.
6. The JSON schema. Consumers of the JSON output depend on the keys `passed`, `total`, `pass_count`, `fail_count`, `records`, `id`, and `failures`. Changing them is a breaking change for any downstream parser.
7. The flat import at line 10. Moving validator.py into a package, or running reporter.py from a different working directory, breaks `from validator import ValidationReport`.
8. The exit-code contract. cli.py catches only `ValueError` and `FileNotFoundError` (cli.py, line 59). A replacement reporter that raises another exception type from `write` would produce a traceback instead of exit code 2.
