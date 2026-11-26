# Todo

## In Progress

- [ ] Smoke test: verify `architekton-warn` mod fires correctly on Claude Code 2.1.331

### Pre-release deploy checklist
- [x] `scripts/preflight.py` -- pre/post-install verification (prerequisites, hooks, skills, mod, import smoke test)
- [x] `docs/windows.md` -- WSL2 requirements and known issues
- [ ] `gh auth login` + `git push github main` -- publish to GitHub
- [ ] Client install on target machine: clone from GitHub, run `scripts/preflight.py --all`

## Backlog

### Phase 1 -- core (required for basic functionality)
- [x] `src/architekton/config.py` -- load/merge global + project config, priority order
- [x] `src/architekton/classifier.py` -- heuristic complexity scorer (no LLM calls)
- [x] `src/architekton/advisor.py` -- CLI: classify, session-start, toggle, status
- [x] `src/architekton/hooks/claude-wrapper.sh` -- session-start model selector wrapper
- [x] `src/architekton/hooks/architekton-warn.sh` -- UserPromptSubmit hook (mismatch advisory)
- [x] `config/global-default.json` -- template for `~/.claude/architekton/config.json`
- [x] `config/project-default.json` -- template for `.claude/architekton.json`
- [x] `install.sh` -- copies wrapper to ~/bin/claude, registers hook, writes global config
- [x] `tests/test_classifier.py` -- unit tests for complexity scoring

### Phase 2 -- project fingerprinting
- [x] `src/architekton/fingerprint.py` -- reads .mkproj, CLAUDE.md, requirements.txt, biases model
- [x] Update `advisor.py session-start` to call fingerprint before recommending

### Phase 3 -- cost journal + reporting
- [x] `src/architekton/journal.py` -- appends session stats to ~/.claude/architekton/cost-journal.jsonl
- [x] Stop hook integration -- calls journal.py at session end
- [x] `advisor.py report [--days N]` -- reads journal, prints model mix + estimated cost per project
- [x] Pricing table in `config/global-default.json` (input/output $/1M tokens per model)

### Phase 4B -- multi-agent job runner
- [x] `src/architekton/orchestrator.py` -- opus decomposes a job into a task DAG
- [x] `src/architekton/runner.py` -- parallel worker execution with ANSI TUI and dependency resolution
- [x] `advisor.py run <job>` -- entry point: plan → execute → summarize
- [x] `config.py` / `global-default.json` -- `job.*` config section
- [x] `/goal` skill: already at user scope (`~/.claude/skills/goal/`), no install needed
- [x] `tests/test_orchestrator.py` + `tests/test_runner.py` -- 37 new tests

### Phase 4 -- advanced features (priority order)
- [ ] `advisor.py set-model <model>` -- convenience wrapper for editing global config
- [ ] Model ladder -- Stop hook detects tool_use_error, bumps recommended tier
- [ ] Budget mode with graceful degradation -- daily_usd + warn_pct config keys
- [ ] Complexity momentum -- session state file, last N prompt scores

### Phase 5 -- polish (all complete as of Nov 2026)
- [x] `scripts/uninstall.sh` -- clean reversal of all install steps
- [x] `advisor.py status` -- human-readable current config + session state
- [x] README.md -- install, usage, config reference, unexplained terms clarified
- [x] `architekton-configure` system command for post-install users
- [x] `scripts/install.sh` / `scripts/uninstall.sh` moved to scripts/ subdirectory
- [x] Benchmark suite (`tests/benchmarks/`) -- cost/speed/quality vs plain claude
- [x] `statusline-command.sh` -- version display fixed to read live from package.json

### Laptop migration (Beastie -> new native-Linux laptop)

Notes moved to responses/migration-notes.md (git-ignored) to keep private network details out of the public repo.

## Done

- [x] Initial scaffold (mkproj)
- [x] Architecture documented (docs/architecture.md)
- [x] Design origin archived (responses/origin-*.txt)
