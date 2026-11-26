# Todo

## In Progress

- [ ] Smoke test: verify `architekton-warn` mod fires correctly on Claude Code 2.1.331

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

### Laptop migration (Beastie -> new native-Linux laptop) -- noted 2026-11-26, deal with later

Beastie = 10.18.254.51. Inventory taken read-only over ssh. Laptop `~/.claude/` currently has no `CLAUDE.md`, no `hooks/`, and a 219-byte `settings.json` with no hooks.

- [ ] Install missing packages (needs sudo): `git python3-venv python3-pip gh`
- [ ] Set git identity; `gh auth login`
- [ ] Fix second git remote: `/ssd-pool/...` does not exist on the laptop; switch to `pat@10.18.254.51:/ssd-pool/home-ext/pat/Repositories/architekton.git`
- [ ] Copy user-scope `~/.claude/CLAUDE.md` from Beastie (17 KB: response format, session archiving, workflow orchestration, release workflow, MemPalace, ASD-STE-100). Back up any laptop copy first. Beastie also has stray `CLAUDE - Copy.md` and `CLAUDE - Copy 10-2026.md` to clean up.
- [ ] Copy hook scripts: `~/.claude/hooks/auto-import-skill.sh`, `~/.claude/hooks/meta-prompt-inject.sh`
- [ ] Re-create hook wiring in laptop `settings.json` (Beastie wires 11 hooks):
  - SessionStart: `~/.local/bin/mempalace-session-context.sh`
  - Stop: `mempalace hook run --hook stop --harness claude-code`; `~/.claude/skills/goal/goal-continue.sh`; `~/.local/bin/mempalace-stop-mine.sh`; smartmodel `cost-journal.sh`; architekton `cost-journal.sh`
  - PreCompact: `mempalace hook run --hook precompact --harness claude-code`
  - UserPromptSubmit: `meta-prompt-inject.sh`; `smartmodel-warn.sh`; `architekton-warn.sh`
  - PostToolUse [Skill]: `auto-import-skill.sh`
- [ ] Hook dependencies to bring over: MemPalace CLI + its two `~/.local/bin` scripts; `skills/goal/`; architekton via `scripts/install.sh`
- [ ] Decide whether the legacy `smartmodel` / `auto_brain` hooks should be retired (architekton replaces them; both run on Beastie today)
- [ ] Review the other Beastie `settings.json` keys before copying: `env`, `permissions`, `enabledPlugins`, `extraKnownMarketplaces`, `statusLine`, `model`, `effortLevel`. Do not copy credentials.
- [ ] Skills (~150 dirs in `~/.claude/skills/`), `agents/`, `keybindings.json`
- [ ] Verify project Stop hooks (`save-response.sh`, `auto-commit.sh`) fire on the laptop; `responses/.last-saved` has not changed since 2026-11-25
- [ ] Run `bash scripts/install.sh` and put `~/bin` ahead of `~/.local/bin` on PATH, so `--mode architekton` works

## Done

- [x] Initial scaffold (mkproj)
- [x] Architecture documented (docs/architecture.md)
- [x] Design origin archived (responses/origin-*.txt)
