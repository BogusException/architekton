# Privacy and Security

## 1. Data handled

auto-brain reads project files at session start (`.mkproj`, `requirements.txt`, `CLAUDE.md`) to fingerprint the project type. It reads prompt text to score complexity. Neither is stored or transmitted.

Phase 3 will add a local cost journal at `~/.claude/smartmodel/cost-journal.jsonl`. This file will contain session metadata: date, project path, model used, and prompt counts. It never leaves the local machine.

No personal data. No network calls. No external services.

## 2. Secret management

auto-brain requires no API keys and uses no `.env` file. The project's `.env.example` is a placeholder from the bootstrap scaffold and can be ignored.

The only file that could contain sensitive data is `~/.claude/smartmodel/cost-journal.jsonl` (Phase 3), which records project paths. That file is local only and git-ignored.

## 3. Access controls

auto-brain runs as the local user. It reads and writes files only in:
- `~/.claude/smartmodel/` (global config and future cost journal)
- `.claude/smartmodel.json` in the project root (project config, if present)

The installer modifies `~/.claude/settings.json` to register the warn hook. No other system files are touched.

## 4. Claude Code boundaries

- Claude must not read or write `~/.claude/smartmodel/cost-journal.jsonl` directly (Phase 3 will own that through `journal.py`).
- Claude must not modify `~/.claude/settings.json` hooks except through `install.sh`.
- No additional restrictions beyond defaults in `.claude/settings.json`.
