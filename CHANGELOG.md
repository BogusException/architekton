# Changelog

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
