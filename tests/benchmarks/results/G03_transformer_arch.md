# transformer.py architecture overview

transformer.py applies an ordered list of named, registered record transformations to a list of dict records and returns the transformed list.

Line numbers refer to `tests/benchmarks/sample_jobs/small_project/transformer.py` unless a file name is given.

## Design patterns

Module-level registry dict. `_REGISTRY` (line 11) maps a step name to a callable of type `Callable[[dict], dict]`. It is private by naming convention only. Nothing stops other code from importing and mutating it.

Registration decorator. `register(name)` (lines 14 to 19) is a decorator factory. The inner `decorator` stores the function in `_REGISTRY[name]` (line 17) and returns it unchanged. The three built-in steps register this way: `normalize_value` (line 22), `strip_whitespace` (line 33) and `add_flag` (line 39). Because the decorator returns the original function, each step can still be called directly, which keeps unit tests simple. Registration happens as an import side effect, so the registry is filled only after the module is imported.

Named-step pipeline. `apply()` (lines 47 to 55) takes step names as strings and runs them in the order given. The loop at lines 53 and 54 makes one full pass over all records per step. It does not run all steps on one record before moving to the next.

Copy-on-transform. `normalize_value` and `add_flag` start with `dict(record)` (lines 25 and 42). `strip_whitespace` builds a new dict with a comprehension (line 36). `apply()` copies the outer list with `list(records)` (line 52). The input records are therefore not mutated. The copies are shallow, so any nested list or dict value is shared between the input and the output. No built-in step touches nested values, but a custom step that mutates one would change the caller's data.

Fail-fast validation. `apply()` checks every step name against the registry before it transforms anything (lines 49 to 51). A bad step name cannot leave half-processed output.

Risk from global registry state. Line 17 assigns into the dict with no check for an existing key. If two functions register under the same name, the later one silently replaces the earlier one. There is no warning, no exception and no log line. This applies to the built-in names as well: a plugin that registers "add_flag" changes the behavior of the default pipeline in `cli.py` (line 16) for the whole process. Import order decides which function wins, so the behavior can change when an unrelated import is added or reordered. The registry is also shared by everything in the process, so tests that register extra steps leak them into later tests unless they clean up `_REGISTRY` themselves.

## Data flow

1. The caller passes `records: list[dict]` and `steps: list[str]` to `apply()` (line 47). In the CLI, `records` comes from the data loader and `steps` comes from the steps argument, which defaults to `DEFAULT_STEPS` (`cli.py` lines 16 and 26 to 30). The call is at `cli.py` line 55.
2. Line 49 builds `unknown: list[str]`, the step names that are not in `_REGISTRY`. Duplicates and order from `steps` are kept.
3. If `unknown` is not empty, line 51 raises `ValueError("Unknown transformations: [...]")`. No record is touched. In the CLI, the `except (ValueError, FileNotFoundError)` clause at `cli.py` line 59 catches this error.
4. Line 52 makes `result: list[dict]`, a new outer list that holds the same record objects as the input.
5. For each step name (line 53), line 54 looks up the callable and builds a new `list[dict]` of its outputs. Each output is a new `dict`. After the first step, `result` no longer shares record objects with the input.
6. The final `list[dict]` is returned. If `steps` is empty, the output is a new list that holds the same record objects as the input, because no step ran.

Order dependency. Each step sees the output of the previous step, so the order matters. The default order in `cli.py` line 16 is `strip_whitespace`, `normalize_value`, `add_flag`.

- `add_flag` (line 43) calls `float(out.get("value", 0))` with no `try` block. It is safe only after `normalize_value` has turned `value` into a float. Without `normalize_value` first, a non-numeric string such as "n/a" raises `ValueError` from inside `add_flag`, and a `None` value raises `TypeError`. The `ValueError` is caught at `cli.py` line 59 and reported as if it were a bad step name. The `TypeError` is not caught there.
- Running `add_flag` before `normalize_value` gives no `flagged` result based on the cleaned number, because the cleaned number does not exist yet.
- `strip_whitespace` has a weaker dependency. It affects only string fields, and `float()` already tolerates surrounding whitespace in a numeric string. If `strip_whitespace` runs after `normalize_value`, the `value` field is already a float and is left alone. Other string fields get stripped either way.
- A missing `value` key is treated as `0` by `normalize_value` (line 27) and `add_flag` (line 43), so the record gets `value` of `0.0` and `flagged` of `False`.

Unknown step name. The function raises `ValueError` at line 51 before any work starts. The message lists all unknown names, not only the first one. There is no suggestion of valid names and no listing of the registry contents.

## External dependencies

Imports in transformer.py:

- `from typing import Callable` (line 8): used only for the type annotations on `_REGISTRY` (line 11), `register` (line 16) and the step signatures. There is no runtime use. The file uses built-in generics (`dict[str, ...]`, `list[dict]`), so it needs Python 3.9 or newer.

There are no third-party packages, no file or network access, and no imports of other project modules.

Callers. `cli.py` is the only sibling module that uses transformer.py. It does `from transformer import apply` (`cli.py` line 11), defines `DEFAULT_STEPS` locally (line 16), and calls `apply(records, args.steps)` (line 55). A grep of the other modules in `small_project` (`data_loader.py`, `validator.py`, `reporter.py`) finds no reference to `transformer`. `cli.py` imports only `apply`, so it never reads `_REGISTRY` or calls `register`.

Coupling that is not an import. `DEFAULT_STEPS` in `cli.py` holds step names as plain strings. If a step is renamed or removed in transformer.py, the CLI fails at run time with the `ValueError` from line 51, not at import time.

## Extending or replacing

Register a new transform:

1. Write a function with the signature `def my_step(record: dict) -> dict:` in transformer.py, or in a new module that imports `register` from transformer.
2. Decorate it with `@register("my_step")`. Pick a name that is not already in `_REGISTRY` (see the duplicate-name risk above).
3. If the function is in a new module, make sure something imports that module before `apply()` runs. `cli.py` imports only `apply`, so a separate plugin module needs an explicit import in `cli.py` or in a loader.
4. Add the name to the steps argument at run time, or to `DEFAULT_STEPS` (`cli.py` line 16) if it should run by default. Put it after any step that it depends on.

Contract for a transform:

- It takes one `dict` and returns a `dict`. `apply()` uses the return value directly (line 54), so a function that returns `None` or edits in place without returning breaks the pipeline.
- It must return a new dict. Use `dict(record)` first, as the built-in steps do. Modifying the input dict would change the caller's data.
- It must not raise for records that earlier steps in the default order allow. Any exception propagates out of `apply()` and aborts the whole run. Only `ValueError` and `FileNotFoundError` are handled by the CLI (`cli.py` line 59).
- It should not depend on being the only step that adds a field. Later steps see its output, so keep field names stable.

Swap the registry for an explicit list of callables:

1. Remove `_REGISTRY` and `register`, or keep them only as a thin helper.
2. Change the signature to `apply(records: list[dict], steps: list[Callable[[dict], dict]]) -> list[dict]`.
3. Replace lines 49 to 55 with a loop over the callables: `result = list(records)`, then `for step in steps: result = [step(r) for r in result]`. The unknown-name check is no longer needed, because a missing step is now a `NameError` or `ImportError` at the place where the list is built.
4. In `cli.py`, change `DEFAULT_STEPS` (line 16) to a list of the function objects: `[strip_whitespace, normalize_value, add_flag]`. Import them from transformer.
5. Decide how the command line selects steps. If users must still type names, build a small `dict` of name to function inside `cli.py`. That brings back a registry, but it is local and explicit, with no import side effects and no cross-module name clashes.

Coupling points that would break:

- The string names. `DEFAULT_STEPS` (`cli.py` line 16) and the `help` text at `cli.py` line 30 use the names that line 22, line 33 and line 39 register. A rename breaks the CLI at run time.
- The `steps: list[str]` parameter type. Callers that pass strings must change if `apply()` takes callables.
- The `ValueError` contract. `cli.py` line 59 turns an unknown name into a clean error message through `except ValueError`. If the explicit-list version removes that error, that handler still catches `ValueError` from inside steps, but a bad step name no longer shares its path.
- The `add_flag` dependency on `normalize_value` (line 43). Any new default order, or any list of callables, must keep `normalize_value` before `add_flag`, or `add_flag` must add its own error handling.
- The import side effect. Code that expects a step to exist after importing transformer.py works only while the decorators run at import time. Moving the built-in steps to another module breaks that.
- The `value` field name. All three built-in steps depend on a field called `value` or on string fields in general (lines 27, 36 and 43). Records with a different schema pass through without error but get wrong or default results.
