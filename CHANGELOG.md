# Changelog

## [Unreleased]

### Added

- `scripts/preflight.py` -- cross-platform pre/post-install verification; checks Python version, jq, Claude Code binary, wrapper integrity, all installed modules and hook scripts, hook registration in `settings.json`, skill directory, and mod status
- `docs/windows.md` -- WSL2 requirements, known issues, and Windows-specific install guidance
- `docs/contributing.md` -- developer setup: venv, git hooks, contributor settings, test commands
- Interactive PATH auto-fix in `scripts/install.sh`: detects shell profile and offers to append `~/bin` during interactive install

### Fixed

- `scripts/install.sh` resolved to its own subdirectory instead of the project root when invoked as `bash scripts/install.sh`; all source file copies failed silently on a fresh clone

## [0.1.0] - 2026-11-26

Initial public release.

### Added

- Automatic model selection (Opus/Sonnet/Haiku) at Claude Code session start via `~/bin/claude` wrapper
- Heuristic complexity classifier -- scores prompts with no LLM calls, no network required
- Project fingerprinting reads `.mkproj`, `CLAUDE.md`, and dependency files to bias model selection
- Per-project cost journal (`~/.claude/architekton/cost-journal.jsonl`) with `architekton report`
- Multi-agent job runner (`architekton run`) with parallel task execution and dependency resolution
- Interactive TUI for configuration (`architekton-configure`)
- `/architekton` skill for in-session job dispatch
- Mid-session mismatch advisory via `UserPromptSubmit` hook
- `architekton-warn` Claude Code mod for in-process model tier warnings
- `scripts/install.sh` and `scripts/uninstall.sh` with backup and clean reversal
- Benchmark suite (`tests/benchmarks/`) for cost/speed/quality comparison

### Known issues

- `UserPromptSubmit` hooks do not receive `CLAUDE_MODEL` in subprocess environments (upstream: anthropics/claude-code#111757). The warn hook reads `ARCHITEKTON_MODEL` exported by the wrapper instead.
