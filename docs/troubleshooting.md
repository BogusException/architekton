# Troubleshooting

## 1. Common errors

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `[auto-brain]` advisory never appears | `~/bin/claude` not on PATH before real `claude` | Add `export PATH="$HOME/bin:$PATH"` to shell profile; verify with `which claude` |
| Wrapper launches but picks wrong model | Project config (``.claude/smartmodel.json``) has an explicit `default_model` | Check `advisor status` -- the source field shows which config won |
| Hook advisory never fires mid-session | Warn hook not registered | Check `.claude/settings.json` for a `UserPromptSubmit` entry pointing to `smartmodel-warn.sh`; re-run `install.sh` if missing |
| `auto_brain: mode must be one of ...` | Invalid `mode` value in a config file | Valid values: `"auto"`, `"advisory"` |
| `auto_brain: <path>: invalid JSON` | Corrupt config file | Check the file named in the error; fix or delete it (`load()` falls back to defaults for missing files) |
| Tests fail with `ModuleNotFoundError` | Running without `PYTHONPATH` set | Use `PYTHONPATH=src python -m unittest discover -s tests` or `bash test.sh` |

## 2. Logs

- The wrapper and hook print diagnostics to stderr when something goes wrong.
- The warn hook is designed to never block a prompt -- any exception is caught and printed to stderr, not surfaced to Claude Code.
- To see what model the wrapper selected: check the `[auto-brain] Starting with ...` line at session start.
- To inspect the full classification result for a prompt: `echo "your prompt" | PYTHONPATH=src python -m auto_brain.advisor classify`

## 3. Getting help

Open an issue in the project repo and include:
- Output of `PYTHONPATH=src python -m auto_brain.advisor status`
- Output of `bash test.sh`
- The full error message, not just the last line
- Python version (`python --version`) and OS
