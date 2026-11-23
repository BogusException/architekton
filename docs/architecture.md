# Architecture

## 1. Overview

architekton is a model-level advisor and cost governor for Claude Code. It automatically selects the right Claude model (Opus / Sonnet / Haiku) at session start based on project type and prompt complexity, warns mid-session when the current model is mismatched for the task, and tracks spend over time.

Claude Code has no built-in automatic model switching. The only native controls are `--model <alias>` at launch, the `"model"` key in `settings.json`, `--fallback-model` (overload only), and `--max-budget-usd` (non-interactive `--print` mode only). architekton fills the gap.

The core constraint: Claude Code has no mid-session model switching API. All automatic selection happens at session start via a wrapper script. Mid-session behavior is advisory -- a `UserPromptSubmit` hook injects a one-line nudge when complexity diverges from the current model.

## 2. Components

| Component | Responsibility | File or module |
|---|---|---|
| Wrapper script | Reads project/global config, picks model, launches `claude --model <x>` | `src/architekton/hooks/claude-wrapper.sh` -> `~/bin/claude` |
| Advisor | CLI entry point: classify, session-start, toggle, status, report, run | `src/architekton/advisor.py` |
| Classifier | Heuristic complexity scorer. No LLM calls. Fast and free. | `src/architekton/classifier.py` |
| Fingerprint | Project-type detector: reads `.mkproj`, `CLAUDE.md`, `requirements.txt` to bias model | `src/architekton/fingerprint.py` |
| Config | Loads global + project configs, merges with priority order | `src/architekton/config.py` |
| Journal | Per-session cost journal read/write | `src/architekton/journal.py` |
| Orchestrator | Calls a high-model to decompose a job into a task DAG | `src/architekton/orchestrator.py` |
| Runner | Executes task DAG with parallel workers and a live ANSI TUI | `src/architekton/runner.py` |
| Warn hook | `UserPromptSubmit` hook: classifies prompt, injects mismatch warning | `src/architekton/hooks/architekton-warn.sh` |
| Journal hook | `Stop` hook: counts turns, appends session record to cost journal | `src/architekton/hooks/cost-journal.sh` |
| Installer | Copies wrapper, registers hooks, writes global config | `install.sh` |

## 3. Config hierarchy (highest to lowest priority)

1. `--model <alias>` passed explicitly on command line -- always wins, wrapper passes it through
2. `.claude/settings.json` `"model"` key (project scope, existing native mechanism)
3. `.claude/architekton.json` (project scope, architekton specific)
4. `~/.claude/architekton/config.json` (global, architekton)
5. `~/.claude/settings.json` `"model"` key (global native)

## 4. Data flow

### Session start
```
user runs: claude [args]
      |
~/bin/claude (wrapper)
      |
      +-- config.py: load ~/.claude/architekton/config.json + .claude/architekton.json
      |     disabled? -> exec real claude directly
      |     explicit --model in args? -> pass through unchanged
      |
      +-- fingerprint.py: scan project files -> bias score
      |     .mkproj present, bash-heavy -> bias toward opus
      |     data science packages in requirements.txt -> sonnet
      |     docs-only, no src/ code -> haiku
      |
      +-- map bias to tier -> model string
      |
      exec real_claude --model <model> [original args]
      prints: [architekton] Starting with opus (project-fingerprint)
```

### Mid-session advisory
```
each user prompt
      |
architekton-warn.sh (UserPromptSubmit hook)
      |
      +-- advisor.py warn parses the hook JSON from stdin (prompt field)
      +-- classifier.py classify -> {score, tier, recommended_model}
      +-- current model: $ARCHITEKTON_MODEL (set by the wrapper), else $CLAUDE_MODEL
      |
      +-- if mismatch:
      |     additionalContext = "[architekton] Complexity suggests <model>
      |                         (you are on <current>). Restart: claude --model <model>"
      |
      +-- if match or disabled:
            additionalContext = ""   (no noise injected)
```

### Session end
```
Stop hook (cost-journal.sh)
      |
      advisor.py session-end (reads JSON payload on stdin)
            |
            counts user-role messages in transcript_path -> turns
            |
            journal.py session_end(model, turns)
            |
            appends one line to ~/.claude/architekton/cost-journal.jsonl:
            {"date":..., "project":..., "model":..., "turns":..., "heavy_prompts":..., "light_prompts":...}
```

### Job runner
```
advisor.py run "Build the auth module"
      |
      orchestrator.py decompose()
            |
            calls: real_claude --print --model opus -p "<decompose_prompt>"
            env: ARCHITEKTON_DISABLE=1
            parses: JSON task list [{id, title, prompt, model, depends_on}, ...]
      |
      runner.py run(tasks, ...)
            |
            task DAG: tasks whose depends_on are all COMPLETE are "ready"
            failed deps -> mark dependents SKIPPED; independent tasks keep running
            |
            for each ready task (up to max_parallel concurrent):
                thread -> real_claude --print --model <task.model> --max-turns N -p "<task_prompt>"
                env: ARCHITEKTON_DISABLE=1
                on complete: status=COMPLETE, write ~/.claude/architekton/jobs/<ts>/<id>.txt
                on failure or timeout: status=ERROR
            |
            main thread redraws ANSI TUI every 100ms:

            ─────────────────────────────────────────────────────────────────────
             architekton  "Build user auth"                      opus 4.7 → workers
            ─────────────────────────────────────────────────────────────────────
              ✓  W1   haiku 4.5       [low ]  Create user model           4.2s
              ⠸  W2   opus 4.7        [high]  Run test suite            42s/300s
              ·  W3   haiku 4.5       [low ]  Write tests                   --
              ✗  W4   haiku 4.5       [low ]  Update README               0.9s
              ↷  W5   sonnet 4.6      [med ]  Write changelog                --
            ─────────────────────────────────────────────────────────────────────
              1 done · 1 running · 2 waiting · 1 error

            Columns: status · worker ID (W#) · model + version · thinking effort ·
                     task title · elapsed time (running: elapsed/max; done: total; timeout: TIMEOUT)
            |
            SIGINT: terminate in-flight subprocesses, mark remaining SKIPPED
            |
            print summary: N complete, N error, N skipped
```

## 5. Complexity scoring

Score range 0.0 -- 1.0, starting from a base of 0.5. Computed in under 50ms with no network calls.
Score maps to a tier with `thresholds` from config: `>= heavy` (0.65) is Opus, `<= light` (0.30) is Haiku, else Sonnet.

| Input signal | Weight |
|---|---|
| Prompt token estimate > 400t (chars / 4) | +0.15 per doubling, capped at +0.30 |
| Prompt token estimate < 80t | -0.15 |
| Heavy-signal pattern match (per distinct pattern) | +0.12 |
| Light-signal pattern match (per distinct pattern) | -0.12 |

Heavy signals: `architect`, `design`, `refactor`, `restructure`, `review`, `audit`, `debug`, `investigate`, `root cause`, `all files`, `across the codebase`, `multi-file`, `security`, `exploit`.

Light signals: `rename`, `typo`, `fix spelling`, `add comment`, `format`, `what is`, `show me`, `list`, `git status`, `run tests`, `single file`, `one line`, `commit message`.

Length uses the whole prompt. Signal patterns scan only the first 800 characters, so pasted logs do not trigger them.

Complexity momentum: if the last `momentum_window` prompts averaged >= heavy threshold, hold at the heavy recommendation for the current prompt even if it scores lower.

## 6. External dependencies

| Dependency | Type | Purpose |
|---|---|---|
| Python 3.9+ stdlib only | local | advisor, classifier, fingerprint, journal, config |
| `jq` | system CLI | `install.sh` edits `~/.claude/settings.json` |
| `claude` binary | system CLI | the real Claude Code binary the wrapper calls |

No third-party Python packages. No network calls in the hot path.

## 7. Novel features (not in any existing tool)

1. **Complexity momentum** -- last N prompt scores persist in session state; heavy run -> stays on Opus.
2. **Project fingerprinting** -- session-start reads project files to pre-bias model before the first prompt.
3. **Budget mode with graceful degradation** -- at 80% of `daily_usd`, recommend one tier down. At 100%, recommend Haiku regardless of complexity.
4. **Model ladder** -- Stop hook detects `tool_use_error` payloads and bumps recommended tier up for the next session.
5. **Weekly spend report** -- `advisor.py report [--days 7]` reads the cost journal and prints model mix + estimated cost per project.
6. **Multi-agent job runner** -- `advisor.py run "<goal>"` lets a high-model orchestrator decompose a job into a dependency-ordered task DAG, then dispatches haiku workers in parallel with a live TUI.
