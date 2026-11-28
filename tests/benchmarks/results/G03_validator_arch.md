# validator.py architecture overview

validator.py runs a registry of named rule functions over a list of record dicts and returns a ValidationReport that reporter.py formats and cli.py uses for the exit code.

All line numbers refer to `tests/benchmarks/sample_jobs/small_project/validator.py` unless a file is named.

## Design patterns

1. **Rule functions.** A rule is a plain function `(dict) -> str | None`. It returns None on pass and a failure message on fail. The contract is the type alias `RuleFunc` (line 11). The three built-in rules are `has_id` (24-28), `value_non_negative` (31-38) and `name_not_empty` (41-45).

2. **Decorator-based registry.** `_RULES` (line 13) is a module-level dict of name to function. The `rule(name)` decorator (16-21) writes into it and returns the function unchanged, so rules can still be called directly. Registration happens as a side effect of importing the module. The registry is global mutable state shared by every caller in the process.

3. **Result objects.** Two dataclasses carry the output: `RecordResult` (48-52) holds `record_id`, `passed` and `failures`. `ValidationReport` (55-60) holds `total`, `passed`, `failed` and `results`. The `ok` property (62-64) is derived from `failed == 0`, so it cannot disagree with the counts unless a caller builds a report by hand.

4. **Accumulate errors, not fail fast (for rule failures).** `validate` (67-93) runs every active rule against every record. The inner loop (77-80) does not stop at the first failing rule, and the outer loop (75-85) does not stop at the first failing record. One report lists all failures, each formatted as `"<rule_name>: <message>"` (line 80).

5. **Fail fast (for programmer errors).** Unknown rule names raise `ValueError` before any record is touched (70-72). An exception raised inside a rule function is not caught and aborts the whole run. Only `value_non_negative` catches its own `TypeError` and `ValueError` (36-37).

6. **Default-to-all selection.** `active_rules = rules or list(_RULES)` (line 69) means None and an empty list both select every registered rule.

## Data flow

1. **Input.** `cli.main` calls `load(args.file)`, then `apply(records, args.steps)` (cli.py:54-55), then `validate` at cli.py:56. `validate` receives `records: list[dict]` and `rules: list[str] | None` (line 67). The rule names come from `--rules`, which defaults to `DEFAULT_RULES` (cli.py:17).
2. **Rule resolution.** `active_rules` becomes a `list[str]` (69). Names not in `_RULES` are collected into `unknown: list[str]` (70) and raise `ValueError` (72).
3. **Per-record checks.** For each `dict` record, each rule is looked up in `_RULES` and called (78). A truthy return is a `str` message. It is prefixed with the rule name and appended to a `list[str]` called `failures` (80).
4. **Per-record result.** Each record becomes a `RecordResult` (81-85). `record_id` is `str(record.get("id", "(no id)"))` (82). `passed` is `not failures` (83).
5. **Aggregation.** `passed` is a sum over results (87). The function returns a `ValidationReport` with `total`, `passed`, `failed = total - passed` and the ordered `results` list (88-93).
6. **Hand-off.** cli.py:57 passes the report to `reporter.write(report, fmt=..., dest=...)`. reporter.py reads `ok`, `total`, `passed`, `failed` and `results`, plus `record_id`, `passed` and `failures` on each result (reporter.py:15-18, 20, 23-26, 37-47). cli.py:58 then exits 0 if `report.ok`, else 1.

Edge cases:

- **Missing keys.**
  - `has_id` treats a missing or falsy `id` as a failure (26). The integer `0` also fails.
  - `name_not_empty` treats a missing `name` as empty and fails (43).
  - `value_non_negative` defaults a missing `value` to 0 (34), so a missing `value` passes. This is lenient on purpose or by accident; the file does not say.
  - A record with no `id` is reported as `"(no id)"` (82).
- **Wrong types.**
  - A non-numeric `value` such as `"abc"` or `None` is caught and reported as "not numeric" (36-37). Numeric strings like `"12"` pass because of `float()` (34). `True` passes as 1.0. `"nan"` passes, because `nan < 0` is False.
  - `name_not_empty` runs `str()` on the value (43), so `name=None` becomes `"None"` and passes.
  - A record that is not a dict raises `AttributeError` on the first `.get` call (26 or 82). cli.py catches only `ValueError` and `FileNotFoundError` (cli.py:59), so this would surface as a traceback.
- **Empty record list.** The loop body never runs. The result is `total=0, passed=0, failed=0, results=[]`, and `ok` is True (vacuous pass). reporter.py then prints "Validation PASSED" with zero counts, and cli.py exits 0.
- **Empty rules list.** `--rules` with no names gives `[]`, which is falsy, so line 69 falls back to all rules instead of running none.
- **Duplicate rule names.** `--rules has_id has_id` runs the rule twice and records the failure twice, because there is no de-duplication.

## External dependencies

Imports inside validator.py (all standard library, no third-party packages):

| Import | Line | Use |
|---|---|---|
| `dataclass` from `dataclasses` | 7 | Decorates `RecordResult` (48) and `ValidationReport` (55). |
| `field` from `dataclasses` | 7 | `default_factory=list` for the mutable list fields (52, 60). |
| `Callable` from `typing` | 8 | Builds the `RuleFunc` alias (11). |

The `str | None` and `list[str]` annotations used throughout need Python 3.10 or newer, since line 11 evaluates `str | None` at import time.

Sibling modules:

- **cli.py** imports `validate` (cli.py:12) and calls `validate(records, args.rules)` (cli.py:56). It hard-codes the rule names in `DEFAULT_RULES` (cli.py:17). It reads `report.ok` for the exit code (cli.py:58). It catches the `ValueError` for unknown rules (cli.py:59) and exits with code 2.
- **reporter.py** imports `ValidationReport` (reporter.py:10) and uses it as a type annotation in `_text_lines` (13), `to_text` (31), `to_json` (35) and `write` (53). It consumes the report's fields and does not import `validate`.
- data_loader.py and transformer.py do not import validator.py. They feed it only through cli.py. validator.py imports no sibling modules.

## Extending or replacing

**Add a rule.**

1. In validator.py, define a function `(record: dict) -> str | None` that returns None on pass and a message on fail. Do not raise for bad data. Handle missing keys with `.get`, as the existing rules do.
2. Decorate it with `@rule("rule_name")`, placed above the `RecordResult` class (before line 48) to keep rules together. The name is the string users type after `--rules`.
3. To make it run by default, add the name to `DEFAULT_RULES` (cli.py:17). Without that step it runs only when named explicitly, because `cli.py` always passes a non-empty list.
4. A rule in another module works if that module is imported before `validate` runs, since registration happens on import. A name collision silently replaces the earlier rule (line 19 has no duplicate check).

**Output contract for a replacement validator.** The replacement must return an object with these attributes, because reporter.py and cli.py read them:

- `ok: bool`, `total: int`, `passed: int`, `failed: int`.
- `results`: an iterable of items, each with `record_id` (printed as-is, any str), `passed: bool` and `failures: list[str]`.

It must also keep `validate(records, rules)` callable with a list of dicts and a list of names or None. Unknown names must raise `ValueError` for cli.py:59 to exit with code 2. reporter.py imports the `ValidationReport` class itself, so a replacement either keeps that class name in `validator` or reporter.py's import changes. The JSON output also fixes the field mapping (`record_id` becomes `id`, `passed` becomes `pass_count`, `failed` becomes `fail_count`) in reporter.py:37-47.

**Swap in a schema library.** The practical route is an adapter that runs the library per record and converts its errors into `RecordResult` and `ValidationReport`, leaving cli.py and reporter.py untouched.

- **jsonschema.** Build a schema with `required: ["id", "name"]` and a `value` of type `number` with `minimum: 0`. Use `Draft202012Validator(schema).iter_errors(record)` per record, and turn each error into `"<path>: <message>"`. Costs: a third-party dependency; strict types (the string `"12"` fails unless the transformer coerces it); a missing `value` fails only if you mark it required, which changes today's behavior; non-empty-after-strip for `name` needs a `pattern` or `minLength` workaround; and the concept of named rules disappears, so `--rules` and `DEFAULT_RULES` need a mapping from rule name to sub-schema, or must be dropped.
- **pydantic.** Define a `Record` model with `id: str`, `name: str` and `value: float = 0`, and call `model_validate` per record. Catch `ValidationError` and read `.errors()` (each has `loc`, `msg`, `type`). Lax mode coerces `"12"` to 12.0, which is closest to the current `float()` behavior. Costs: a third-party dependency; error text changes, so anything that matches current message strings breaks; empty-string checks and `value >= 0` need `Field` constraints or validators; `--rules` selection is lost the same way; a non-dict record raises a `ValidationError` instead of an `AttributeError`, which is an improvement.
- Either library adds roughly 30 to 50 lines of adapter code. It trades the 45-line rule section (lines 11-45) for a declarative schema, and gains declarative types and nested validation. It loses per-rule selection from the CLI and the stdlib-only footprint.

**Coupling points that would break.**

1. `_RULES` name strings duplicated in `DEFAULT_RULES` (cli.py:17) and in the `@rule(...)` decorators (24, 31, 41). Renaming a rule needs edits in both files.
2. Failure message format `"<rule>: <message>"` (line 80). It flows straight to reporter.py:26-27 and the JSON `failures` array, so any consumer of that JSON sees a change.
3. `ValueError` for unknown rules (72), caught at cli.py:59. A different exception type would produce a traceback.
4. The attribute names on `ValidationReport` and `RecordResult` (48-64), read in reporter.py and cli.py:58.
5. Module-level import style (`from validator import ...`, cli.py:12 and reporter.py:10). These are flat imports, so the files must run from the same directory or with it on `sys.path`.
6. The vacuous pass on empty input (`ok` True when `failed == 0`). A replacement that treats zero records as an error changes the cli.py exit code from 0.
