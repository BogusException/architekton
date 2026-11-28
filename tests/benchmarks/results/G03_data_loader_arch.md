# data_loader.py architecture overview

data_loader.py reads a CSV or JSON file from disk and returns its contents as a list of record dicts for the rest of the small_project pipeline.

## Design patterns

1. Format dispatch by file extension. `load` (lines 38-45) builds a `Path` (line 40), compares `p.suffix` to ".csv" (line 41) and ".json" (line 43), and calls the matching loader. The comparison is case-sensitive, so ".CSV" is rejected.
2. Loader functions with a shared signature and return shape. `load_csv` (lines 15-26) and `load_json` (lines 29-35) both take `path: str` and return `list[dict]`. `load` has the same signature, so a caller can use any of the three.
3. Single public entry point. `load` is the only function `cli.py` imports (cli.py line 10). The two format loaders are public by name but not used outside the module.
4. Fail-fast validation inside the loader. `load_csv` checks the header set against the module constant `REQUIRED_COLUMNS` (line 12) before it reads any row (lines 20-23). `load_json` checks that the top-level value is a list (lines 33-34). Both raise `ValueError` with a message meant for the user.
5. Module-level constant as schema. `REQUIRED_COLUMNS` (line 12) is the only schema definition. It is checked for CSV only. JSON gets no column check.
6. Context-managed file handles. Both loaders use `with open(...)` (lines 18 and 31), so the file closes on every exit path.

There is no class, no registry, and no shared base. The dispatch is a hard-coded `if` chain, unlike the decorator registry in transformer.py.

## Data flow

1. `cli.py` calls `load(args.file)` (cli.py line 54). The input is a `str` path.
2. `load` (line 38) wraps the string in a `pathlib.Path` and reads `p.suffix`, a `str`.
3. For ".csv", `load_csv(path)` runs.
   - `open(path, newline="")` returns a text file handle (line 18).
   - `csv.DictReader` wraps it (line 19). `reader.fieldnames` is read into a `set[str]` (line 20). A file with no header row gives an empty set.
   - `REQUIRED_COLUMNS - headers` gives the missing names (line 21). If any exist, `ValueError` is raised (line 23).
   - Each row, an `OrderedDict` or `dict` depending on the Python version, is copied with `dict(row)` into a plain `dict[str, str]` (line 25).
   - The function returns `list[dict]` (line 26).
4. For ".json", `load_json(path)` runs.
   - `open(path)` returns a text file handle (line 31).
   - `json.load` returns whatever the file holds: `dict`, `list`, `str`, number, or `None` (line 32).
   - If the result is not a `list`, `ValueError` is raised (lines 33-34). Otherwise the list is returned as is (line 35).
5. `cli.py` passes the returned list to `apply` in transformer.py (cli.py line 55).

Failure cases:

- Missing file with a known extension: `open` raises `FileNotFoundError` (lines 18 or 31). `cli.py` catches it (cli.py line 59) and exits with code 2.
- Missing file with an unknown extension: `load` raises `ValueError` first (line 45), because the extension check runs before any file access. The file is never opened.
- Unknown or absent extension: `ValueError("Unsupported file type: <suffix>")` (line 45). A file with no extension gives an empty suffix in the message.
- CSV with missing required columns, or an empty CSV file: `ValueError` listing the sorted missing names (line 23).
- JSON that is not valid: `json.JSONDecodeError` is a subclass of `ValueError`, so `cli.py` catches it as is.
- JSON whose top level is not an array: `ValueError` naming the actual type (line 34).
- Not handled in the module or in `cli.py`: `PermissionError`, `IsADirectoryError`, `csv.Error`, and non-UTF-8 content under a non-UTF-8 locale default. `UnicodeDecodeError` is a `ValueError` subclass, so `cli.py` catches it. The others escape as a traceback.
- Not checked: JSON array items are never checked to be dicts, and JSON records are never checked for `REQUIRED_COLUMNS`. A CSV row shorter than the header gets `None` for the missing keys. A row longer than the header gets its extra values under the key `None`.

## External dependencies

| Import | Line | Use |
|---|---|---|
| `csv` | 7 | `csv.DictReader` in `load_csv` (line 19) |
| `json` | 8 | `json.load` in `load_json` (line 32) |
| `pathlib.Path` | 9 | `Path(path).suffix` in `load` (line 40) |

All three are standard library. data_loader.py imports no sibling module.

Sibling modules that depend on data_loader.py:

- cli.py imports `load` (line 10) and calls it once (line 54). It is the only dependent.
- transformer.py, validator.py, and reporter.py do not import data_loader. They depend on it only through the record shape that `cli.py` passes along.

## Extending or replacing

Add a new input format, for example YAML or Parquet:

1. Write `load_yaml(path: str) -> list[dict]` (or `load_parquet`) next to `load_json`. Open the file, parse it, and return a list of dicts.
2. Raise `ValueError` for bad structure, so `cli.py` keeps its exit code 2 path (cli.py line 59).
3. Add a branch to `load`, for example `if p.suffix in (".yaml", ".yml"): return load_yaml(path)`, before the `raise` on line 45.
4. Decide whether to enforce `REQUIRED_COLUMNS`. Only `load_csv` does today. Without the check, a record with no "id" reaches validator.py, which reports it per record instead of failing the load.
5. Convert values on purpose. CSV gives only strings. YAML and Parquet give typed values (numbers, `None`, datetimes). The downstream code was only exercised with strings from CSV and with whatever JSON holds.
6. Parquet and YAML need third-party packages (for example `pyarrow`, `PyYAML`). The project rule is stdlib only in the hot path, so import them inside the new function, not at module level.
7. Update the "CSV and JSON" docstring (lines 1-5) and the error message on line 45.

Contract a replacement loader must keep:

- Signature `load(path: str) -> list[dict]`, exported from a module named `data_loader` (cli.py line 10).
- Return type: a `list` of `dict`. It must be a real `list`, because `apply` copies it with `list(records)` and indexes it.
- Key type: `str`. The keys "id", "name", "value", and "timestamp" must be present, because validator.py reads "id", "name", and "value" with `record.get(...)`.
- Value types: CSV gives `str` for every value. `value` must be convertible by `float(...)` (transformer.py lines 27 and 43, validator.py line 34). `name` is passed through `str(...)`. `id` is tested for truthiness. A numeric `value` from JSON works as well. Non-numeric `value` is tolerated: `normalize_value` sets it to 0.0 (transformer.py line 29) and `value_non_negative` reports it (validator.py line 37).
- Errors: raise `ValueError` or `FileNotFoundError` for expected failures. Any other exception type skips the `except` at cli.py line 59 and prints a traceback.

Coupling points that would break:

- The import `from data_loader import load` (cli.py line 10). Renaming the module or the function breaks it.
- The `except (ValueError, FileNotFoundError)` clause (cli.py line 59). A loader that raises another type, such as a custom `LoadError` that does not subclass `ValueError`, produces a traceback and exit code 1 from Python instead of the intended exit code 2.
- The record shape in transformer.py and validator.py. They read "value", "name", and "id" by literal key name. A loader that renames columns, nests records, or returns a dict of lists breaks them.
- A generator return. `apply` calls `list(records)`, which would still work, but cli.py has no other consumer that needs a list, so a lazy loader would also hide errors until a later stage. Keep the eager list.
- `REQUIRED_COLUMNS` (line 12) is local to this module. Nothing else imports it, but validator.py rules assume the same four names.
