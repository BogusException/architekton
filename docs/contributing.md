# Contributing

## Dev setup

Requires Python 3.9+, `jq`, and Claude Code.

```bash
git clone https://github.com/theitguys/architekton.git
cd architekton
bash dev-install.sh
```

`dev-install.sh` creates a `.venv`, installs the package in editable mode with dev dependencies, sets `core.hooksPath` to `.githooks` (the private-path commit guard), and generates `.claude/settings.local.json` with the contributor-only Claude Code hooks (auto-test, format-on-save, save-response, auto-commit).

## Dev commands

| Command | Purpose |
|---|---|
| `bash dev-configure.sh` | Open the interactive config editor against the dev config |
| `bash dev-run.sh` | Print current config and detected session model |
| `bash dev-test.sh` | Run the full test suite |
| `bash dev-uninstall.sh` | Remove the venv |
| `bash scripts/install.sh` | Install architekton system-wide from this clone |
| `bash scripts/uninstall.sh` | Remove the system install |

## Project layout

```
src/architekton/     Python package (classifier, advisor, journal, orchestrator, runner)
src/architekton/hooks/  Shell hooks installed into ~/.claude/architekton/lib/
src/mod/             Claude Code mod (architekton-warn in-process hook)
skills/architekton/  /architekton slash command skill
config/.defaults/    Default config templates copied on first install
scripts/             install.sh and uninstall.sh (end-user scripts)
tests/               pytest suite
docs/                Documentation
```

## Running tests

```bash
bash dev-test.sh
```

Or directly:

```bash
.venv/bin/pytest tests/
```

## Commit rules

The `.githooks/pre-commit` guard (enabled by `dev-install.sh`) rejects commits that contain private paths. If your commit is blocked unexpectedly, check `.githooks/private-paths.sh` for the pattern list.

Stage specific files explicitly rather than `git add -A` -- the auto-commit Stop hook follows the same rule.

## Architecture

See [architecture.md](architecture.md) for the full design. The short version:

- The `~/bin/claude` wrapper selects a model at session start and exports `ARCHITEKTON_MODEL`.
- The `architekton-warn.sh` UserPromptSubmit hook fires on every prompt and emits a one-line advisory if the running model does not match the complexity of the current prompt.
- The `cost-journal.sh` Stop hook appends session stats to `~/.claude/architekton/cost-journal.jsonl` at session end.
- `architekton status` / `architekton report` read the journal and config for human-readable output.
