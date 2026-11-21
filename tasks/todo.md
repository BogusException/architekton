# Todo

## In Progress

- [ ] 

## Backlog

### Phase 1 -- core (required for basic functionality)
- [x] `src/auto_brain/config.py` -- load/merge global + project config, priority order
- [x] `src/auto_brain/classifier.py` -- heuristic complexity scorer (no LLM calls)
- [x] `src/auto_brain/advisor.py` -- CLI: classify, session-start, toggle, status
- [x] `src/auto_brain/hooks/claude-wrapper.sh` -- session-start model selector wrapper
- [x] `src/auto_brain/hooks/smartmodel-warn.sh` -- UserPromptSubmit hook (mismatch advisory)
- [x] `config/global-default.json` -- template for `~/.claude/smartmodel/config.json`
- [x] `config/project-default.json` -- template for `.claude/smartmodel.json`
- [x] `install.sh` -- copies wrapper to ~/bin/claude, registers hook, writes global config
- [x] `tests/test_classifier.py` -- unit tests for complexity scoring

### Phase 2 -- project fingerprinting
- [x] `src/auto_brain/fingerprint.py` -- reads .mkproj, CLAUDE.md, requirements.txt, biases model
- [x] Update `advisor.py session-start` to call fingerprint before recommending

### Phase 3 -- cost journal + reporting
- [ ] `src/auto_brain/journal.py` -- appends session stats to ~/.claude/smartmodel/cost-journal.jsonl
- [ ] Stop hook integration -- calls journal.py at session end
- [ ] `advisor.py report [--days N]` -- reads journal, prints model mix + estimated cost per project
- [ ] Pricing table in `config/global-default.json` (input/output $/1M tokens per model)

### Phase 4 -- advanced features
- [ ] Complexity momentum -- session state file, last N prompt scores
- [ ] Budget mode with graceful degradation -- daily_usd + warn_pct config keys
- [ ] Model ladder -- Stop hook detects tool_use_error, bumps recommended tier
- [ ] `advisor.py set-model <model>` -- convenience wrapper for editing global config

### Phase 5 -- polish
- [ ] `install.sh --uninstall` -- clean reversal of all install steps
- [ ] `advisor.py status` -- human-readable current config + session state
- [ ] README.md -- install, usage, config reference

## Done

- [x] Initial scaffold (mkproj)
- [x] Architecture documented (docs/architecture.md)
- [x] Design origin archived (responses/origin-*.txt)
