# cli.py architecture overview

`cli.py` is the command-line entry point that parses arguments and runs the load, transform, validate and report pipeline for one data file.

Line numbers refer to `tests/benchmarks/sample_jobs/small_project/cli.py` (65 lines). Calls into the sibling modules were checked against their signatures only.

## Design patterns

1. Orchestration facade. `main()` (lines 20-61) holds no data logic. It calls one function from each sibling module and passes the result to the next. All parsing, transformation, validation and formatting live elsewhere.
2. Linear pipeline. Lines 54-57 chain four calls: `load(args.file)`, `apply(records, args.steps)`, `validate(records, args.rules)`, `write(report, ...)`. Each stage takes the previous stage's output. The variable `records` is rebound at line 55, so the loaded list is not kept.
3. Default configuration constants. `DEFAULT_STEPS` (line 16) and `DEFAULT_RULES` (line 17) are module-level lists. They feed the argparse defaults at lines 28 and 35 and the help text at lines 30 and 37, so the help text cannot drift from the real defaults.
4. Names as configuration (late binding). `--steps` and `--rules` carry plain strings. `cli.py` never imports a transformation or a rule function. `transformer.apply` and `validator.validate` look the names up in their own registries (`_REGISTRY` and `_RULES`), so a new step or rule needs no change in `cli.py`.
5. Declarative argument parsing. `argparse.ArgumentParser` is built inside `main()` (lines 21-50): one positional `file` (line 24) and four options, `--steps` (25-31), `--rules` (32-38), `--format` (39-44, restricted by `choices`) and `--output` (45-50). Parsing runs at line 51.
6. Single error boundary. One `try` block (lines 53-61) wraps the whole pipeline. One `except (ValueError, FileNotFoundError)` clause (line 59) turns expected failures into a message and exit code 2.
7. Exit-code contract. Line 58 maps `report.ok` to exit 0 or 1. Line 61 uses exit 2 for usage and input errors. This lets shell scripts tell "data is invalid" from "run failed".
8. Script guard. Lines 64-65 call `main()` only when the file runs as a script, so tests can import the module without side effects.

## Data flow

1. Command line. `sys.argv` is a list of strings. `parser.parse_args()` (line 51) returns an `argparse.Namespace` named `args`.
2. `args` fields:
   - `args.file`: `str`, a path.
   - `args.steps`: `list[str]`, default `DEFAULT_STEPS`.
   - `args.rules`: `list[str]`, default `DEFAULT_RULES`.
   - `args.format`: `str`, either `"text"` or `"json"`.
   - `args.output`: `str | None`, `None` means stdout.
3. `load(args.file)` (line 54, `data_loader.load`). Input is the path string. Output is `list[dict]`, one dict per record. The function picks the CSV or JSON reader from the file extension. It raises `ValueError` for any other extension.
4. `apply(records, args.steps)` (line 55, `transformer.apply`). Input is `list[dict]` and `list[str]`. Output is a new `list[dict]`. Each named step runs over every record, in the order given. It raises `ValueError` if a step name is not registered.
5. `validate(records, args.rules)` (line 56, `validator.validate`). Input is `list[dict]` and `list[str]`. Output is a `ValidationReport` dataclass with `total`, `passed`, `failed`, a `results` list of `RecordResult`, and an `ok` property (`failed == 0`). It raises `ValueError` if a rule name is not registered.
6. `write(report, fmt=args.format, dest=args.output)` (line 57, `reporter.write`). Input is the `ValidationReport`, a format string and an optional path. It renders text or JSON. It writes the result to the file at `dest`, or prints to stdout when `dest` is `None`. It returns nothing that `cli.py` uses.
7. Exit. Line 58 calls `sys.exit(0 if report.ok else 1)`. Exit 0 means every record passed every rule. Exit 1 means at least one record failed.
8. Errors. If a stage raises `ValueError` or `FileNotFoundError`, control jumps to line 59. Line 60 prints `error: <message>` to stderr and line 61 exits with code 2. Causes include:
   - an unsupported file extension (`ValueError` from `load`),
   - an unknown step or rule name (`ValueError` from `apply` or `validate`),
   - a missing input file (`FileNotFoundError` from `load`),
   - a missing parent directory for `--output` (`FileNotFoundError` from `write`),
   - malformed JSON input, or a JSON file whose top level is not an array. `load_json` calls `json.load` without a handler, and `json.JSONDecodeError` is a subclass of `ValueError`. It also raises `ValueError` itself for a non-array top level.
9. Not handled. Other exceptions, such as `PermissionError` on the input or output file, are not caught. Python prints a traceback and exits with code 1, which is the same code as "validation failed".
10. `sys.exit()` raises `SystemExit`, which is not a `ValueError`, so the call at line 58 inside the `try` block is not swallowed by the `except` clause.

Two argparse behaviors affect the flow. `--steps` with no values gives `[]`, so no transformation runs. `--rules` with no values gives `[]`, and `validate` treats an empty list as "run all registered rules" (`rules or list(_RULES)`), so it runs more rules, not fewer.

## External dependencies

Standard library imports:

| Line | Import | Use in `cli.py` |
| --- | --- | --- |
| 7 | `argparse` | Builds the parser and reads `sys.argv` (lines 21-51). |
| 8 | `sys` | `sys.exit` for exit codes (lines 58, 61) and `sys.stderr` for error output (line 60). |

Internal imports from sibling modules in the same directory:

| Line | Import | Use in `cli.py` |
| --- | --- | --- |
| 10 | `data_loader.load` | Reads a CSV or JSON file into `list[dict]` (line 54). |
| 11 | `transformer.apply` | Runs named transformation steps over the records (line 55). |
| 12 | `validator.validate` | Runs named rules and returns a `ValidationReport` (line 56). |
| 13 | `reporter.write` | Formats the report and sends it to a file or stdout (line 57). |

The internal imports are bare module names (`from data_loader import load`), not package-relative imports. They work only when the directory containing `cli.py` is on `sys.path`, which is true when the script runs as `python cli.py` from any location (Python puts the script's directory first on the path), or when a test adds that directory to `sys.path`. They fail if `cli.py` is imported as part of a package. `cli.py` also depends on `report.ok` (a `ValidationReport` property), although it does not import that class.

## Extending or replacing

### Add a command-line option

1. Add a `parser.add_argument(...)` call in `main()` between lines 21 and 50, before `parse_args()` at line 51.
2. If the option has a default that the help text should show, add a module constant next to lines 16-17 and use it for both `default=` and the f-string in `help=`, as lines 28-30 do.
3. Read the value as `args.<name>` inside the `try` block and pass it to the stage that needs it (lines 54-57).
4. If the receiving function does not yet accept the value, change its signature in the sibling module. For example, a `--delimiter` option needs a new parameter on `data_loader.load`, and `load` would also need to pass it to `load_csv`.
5. Decide which exit code a bad value should give. A `ValueError` raised in a stage already gives exit 2.

Coupling points that break:
- The `write(report, fmt=args.format, dest=args.output)` call (line 57) uses keyword names `fmt` and `dest`. Renaming them in `reporter.write` breaks the call.
- `--format` has `choices=["text", "json"]` (line 41) and `reporter.write` has its own `fmt == "json"` test. Adding a third format needs changes in both places, and `write` silently treats any unknown value as text.

### Add a pipeline stage

1. Write the stage as a function in a sibling module, or a new one. Define its input and output as plain types (`list[dict]` in, `list[dict]` out for a record stage).
2. Import it at the top (lines 10-13 are the pattern).
3. Call it in the `try` block at the right position in lines 54-57. A record stage goes between lines 55 and 56. A stage that works on the report goes between lines 56 and 57.
4. If the stage is configurable, add an option as described above.
5. Raise `ValueError` for bad configuration so the handler at line 59 gives exit 2.

If the new stage is only another transformation or validation rule, do not touch `cli.py`. Register the function in `transformer` (decorator `@register("name")`) or `validator` (decorator `@rule("name")`) and pass its name with `--steps` or `--rules`. To make it run by default, add the name to `DEFAULT_STEPS` or `DEFAULT_RULES` (lines 16-17).

Coupling points that break:
- Stages are connected by position. `validate` expects `list[dict]`, so a stage between lines 55 and 56 that returns another type breaks it.
- `write` expects a `ValidationReport`, and line 58 reads `report.ok`. A stage that replaces the report must keep `ok`.
- `except (ValueError, FileNotFoundError)` (line 59) is the whole error policy. A new stage that raises `KeyError`, `OSError` subclasses or a custom exception produces a traceback unless the tuple is extended.

### Replace cli.py with another entry point

1. Keep the four calls and their order: `load`, `apply`, `validate`, `write` (lines 54-57). A web handler, a scheduler or a test harness can call the same functions directly.
2. Reuse `DEFAULT_STEPS` and `DEFAULT_RULES`, or define new defaults. Importing them from `cli.py` pulls `argparse` in, so copy them or move them to a shared module.
3. Decide how to report failure. Return the `ValidationReport` or its `ok` value instead of calling `sys.exit`, and translate `ValueError` and `FileNotFoundError` into whatever the new caller expects (HTTP 400 or 404, a log line, a retry).
4. Make sure the sibling modules are importable. The bare imports need their directory on `sys.path`.

Coupling points that break:
- `main()` takes no arguments and reads `sys.argv` through `parse_args()` (line 51). It cannot be called from other code with explicit values, so a second entry point must not call `main()`.
- `sys.exit` at lines 58 and 61 ends the process. Calling `main()` from a long-running service stops the service.
- `reporter.write` prints to `sys.stdout` when `dest` is `None`. A caller that needs the text as a string should call `reporter.to_text(report)` or `reporter.to_json(report)` instead.
- Exit codes 0, 1 and 2 are a contract with shell callers. Any replacement used in scripts must keep them.
