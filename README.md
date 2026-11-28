# architekton

- You're paying **Opus/Fable prices** for tasks Haiku would handle fine. *(Opus and Fable are Anthropic's highest-capability -- and most expensive -- Claude model tiers.)*
- You want to pay **Opus prices** for *planning*, *reasoning*, and *thinking*, but pay **Haiku prices** for the tactical *doing*. 
- You want to automatically have the LLM:
    - **Parallel operations** at scale
    - Have the LLM only use the **lowest cost model** it needs to think, and... 
    - Use the **lowest cost model** needed to do the grunt-work, ...
    - All while **auto-adjusting** to the work/objective/prompt(s).

<div align="center"> 

#### But How?</div>

**architekton** wraps the `claude` CLI to automatically select the right model at session start, warns you mid-session when complexity changes, runs multi-agent jobs where an Opus planner dispatches parallel Haiku workers, and tracks per-project spend in a cost journal. No network calls. Classification runs in under 50 ms.

---

## Why this exists

Opus costs roughly 19x more than Haiku. Most Claude Code sessions don't need Opus. When you're renaming a variable, adding a docstring, or running `git status`, you're burning Opus tokens for work Haiku would finish just as fast.

architekton measures the work in front of you, picks the model that fits, and nudges you when that changes mid-session. It doesn't require you to think about models -- it just handles it.

---

## Install

```bash
bash scripts/install.sh
```

Requires Python 3.9+, Claude Code, and `jq`. The installer checks for all three before touching anything and exits with a clear message if one is missing -- no partial install to clean up. On most Linux systems `jq` is available via `apt install jq` or `dnf install jq`; on macOS via `brew install jq`. See https://jqlang.github.io/jq/ for all platforms. The installer:

1. Places a wrapper at `~/bin/claude` that intercepts every session start
2. Registers a `UserPromptSubmit` hook for mid-session complexity scoring
3. Registers a `Stop` hook to record session stats in the cost journal
4. Installs the `architekton-warn` Claude Code mod plugin

**Claude Code hooks** are shell scripts that Claude Code calls automatically at defined points in a session -- before a prompt is submitted, after the session ends, etc. architekton uses two: one to score each prompt as you type it, and one to record session stats when you close Claude Code.

**Claude Code mods** are JavaScript plugins that Claude Code loads at startup. They have access to session internals (like the active model) that shell hooks don't. architekton's mod (`architekton-warn`) uses this to inject complexity warnings directly into the prompt context.

After install, open a new shell (so `~/bin/claude` takes precedence over the system binary) and start Claude Code as normal. **architekton** operates silently in the background.

For full prerequisites and manual verification steps, see `docs/install.md`.

To remove everything:

```bash
bash scripts/uninstall.sh
```

---

## Configuring architekton

The installer places a `architekton-configure` command on your PATH. Run it any time you want to change settings:

```bash
architekton-configure
```

This opens the interactive TUI (Terminal User Interface) config editor. Use the arrow keys to move between fields and type to change a value. When you're done:

- Press `s` to save and exit.
- Press `q` to exit without saving.

Your config is stored at `~/.claude/architekton/config.json`. The editor shows you every available option, its current value, and a short description of what it controls. You never need to edit the JSON file by hand.

To configure a specific project (settings that override your global config only for that directory):

```bash
cd /path/to/your/project
architekton-configure
```

architekton detects the working directory and writes a project-level config alongside the global one. The global config applies everywhere; the project config applies only inside that directory.

---

## What it is

### 1. Description

Arkitekton is two Claude Code primitives composed together:

  1. A shell wrapper -- a script installed at ~/bin/claude that sits in front of the real
  claude binary. Every claude invocation goes through it. This is the session-start model
  selector.
  2. Claude Code hooks -- two of them, registered in ~/.claude/settings.json:
    - UserPromptSubmit hook: fires on each prompt, runs architekton-warn.sh -> advisor.py warn
    - Stop hook: fires at session end, runs cost-journal.sh -> advisor.py session-end

  The Python package (advisor.py, classifier.py, etc.) is not itself a Claude component type
  -- it's the internal logic those two primitives call out to.

  The job runner adds a third usage pattern: it spawns claude --print subprocesses directly
  (non-interactive mode), making those instances act as workers dispatched by the
  orchestrator. That's not a new primitive type; it's just invoking the binary
  programmatically.

### 2. Bottom line?

So the complete answer: shell wrapper + two hooks + subprocess invocations of the binary. No
   skills, no agents, no MCP servers.

---

## What it does

### 1. Automatic model selection at session start

Before launching Claude Code, the wrapper calls `advisor.py session-start`. This checks two signals in order:

- **Project fingerprint**: scans the project directory for known patterns
  - Bash-heavy `.mkproj` -> Opus
  - Data science packages in `requirements.txt` (numpy, pandas, torch, etc.) -> Sonnet
  - Docs-only project with no source files -> Haiku
- **Complexity thresholds**: if no fingerprint matches, the default model from config applies

The selected model is passed to Claude Code via `--model`. If **architekton** is disabled or in advisory mode, Claude Code starts unchanged.

### 2. Mid-session complexity warnings

Every prompt you submit is scored by a heuristic classifier (no LLM, no network). The classifier looks at prompt length and vocabulary signals:

- Architecture, refactor, review, security, debug, root cause -> heavier
- Rename, typo, format, list, show me, run tests -> lighter

When the active model is mismatched for the detected complexity, architekton injects a one-line nudge via the `UserPromptSubmit` hook:

```
[architekton] Complexity suggests haiku (you are on sonnet). Switch: /model haiku
```

The nudge appears above your prompt. It never blocks or delays your message.

### 3. Multi-agent job runner

One command decomposes a goal into a set of tasks ordered by their dependencies, then dispatches parallel Claude Code sessions -- one per task -- and displays a live TUI:

```
─────────────────────────────────────────────────────────────────────────────
 architekton  "Build user auth API"   opus → workers
─────────────────────────────────────────────────────────────────────────────
  ✓  orch  opus 4.7         [high]  DONE  orchestrator  (4 tasks planned)   2.1s
  ✓  W1    haiku 4.5        [low ]  DONE  Create user model                18.4s
  ✓  W2    haiku 4.5        [low ]  DONE  Write auth endpoints             31.2s
  ⠸  W3    haiku 4.5        [low ]  RUN   Write tests                   14s/300s
  ·  W4    haiku 4.5        [low ]  PEND  Update OpenAPI spec                 --
─────────────────────────────────────────────────────────────────────────────
  2 complete · 1 running · 1 waiting
```

The orchestrator (Opus by default) plans the work. Workers (Haiku by default) execute in parallel. Task output is saved per-worker to `~/.claude/architekton/jobs/<timestamp>/<task_id>.txt`.

Dependencies between tasks are respected -- a worker won't start until its dependencies complete. If a dependency errors, downstream tasks are skipped.

### 4. Cost journal

Every session end records project name, model, and turn count to a JSONL journal at `~/.claude/architekton/cost-journal.jsonl`. JSONL (JSON Lines) is a plain-text format where each line is a self-contained JSON object -- one line per session, easy to tail, grep, or parse with any tool. The report command shows estimated spend by project:

```
$ python -m architekton.advisor report --days 7

Cost journal  --  last 7 days  (12 sessions, estimated costs)

project                         sessions   turns  model mix             est. cost
------------------------------------------------------------------------
architekton                            5      87  O:40% S:40% H:20%     $   8.21
my-web-app                             4      61  S:75% H:25%           $   2.14
docs-site                              3      22  H:100%                $   0.07
```

Pricing is configurable per model tier. The journal uses rough per-turn token estimates; treat the numbers as directional, not billing-exact.

---

## CLI reference

```bash
# Score a prompt
echo "refactor the auth module" | python -m architekton.advisor classify

# Show what model the wrapper would select (and why)
python -m architekton.advisor session-start

# Show current config and session state
python -m architekton.advisor status

# Spend report (last 7 days)
python -m architekton.advisor report --days 7

# Spend report (all time)
python -m architekton.advisor report

# Run a multi-agent job
python -m architekton.advisor run "Build a REST API for user authentication"

# Run with explicit models and parallelism
python -m architekton.advisor run "Migrate the database schema" \
  --orchestrator-model opus \
  --worker-model sonnet \
  --max-parallel 6 \
  --timeout 600

# Force all workers to a specific thinking level
python -m architekton.advisor run "Review and harden the security model" \
  --thinking high

# Disable globally
python -m architekton.advisor toggle off

# Re-enable
python -m architekton.advisor toggle on
```

For a single session bypass without changing config:

```bash
ARCHITEKTON_DISABLE=1 claude
```

---

## Configuration

Global config lives at `~/.claude/architekton/config.json`. Project overrides go in `.claude/architekton.json` in your project root. Project values win over global values.

| Key                      | Default                                 | Description                                                          |
| ------------------------ | --------------------------------------- | -------------------------------------------------------------------- |
| `enabled`                | `true`                                  | Set `false` to disable without uninstalling                          |
| `mode`                   | `"auto"`                                | `"auto"` selects model at start; `"advisory"` only warns mid-session |
| `default_model`          | `"sonnet"`                              | Fallback when no fingerprint matches                                 |
| `thresholds.light`       | `0.30`                                  | Complexity at or below this -> Haiku                                 |
| `thresholds.heavy`       | `0.65`                                  | Complexity at or above this -> Opus                                  |
| `job.orchestrator_model` | `"opus"`                                | Model used to plan a job                                             |
| `job.worker_model`       | `"haiku"`                               | Default model for each task worker                                   |
| `job.max_parallel`       | `4`                                     | Maximum concurrent worker sessions                                   |
| `job.worker_timeout`     | `300`                                   | Seconds before a worker session is killed                            |
| `job.worker_max_turns`   | `20`                                    | Max turns per worker session                                         |
| `job.thinking_map`       | `{haiku: low, sonnet: med, opus: high}` | Maps model tier to thinking effort                                   |
| `job.worker_thinking`    | `""`                                    | Force all workers to a fixed effort level                            |

**Thinking effort levels:** `low`, `med`, `high`, `ext`. These are passed to Claude Code as the extended thinking budget. Unknown values pass through with a warning; common aliases (`medium`, `extreme`, `max`) are silently normalized.

**Model values** accept short aliases (`haiku`, `sonnet`, `opus`) or full model IDs (`claude-opus-4-7`, `claude-haiku-4-5-20251001`).

**TUI colors** are configurable under the `tui` key. Each status and model family has a named color slot that accepts any named ANSI color (`cyan`, `bright_green`, etc.) or an `rgb(R,G,B)` value.

To wire in the native `/plan` skill as the orchestrator preamble:

```json
"job": { "orchestrator_preamble": "/plan\n" }
```

Full config reference with all keys and extension points: `docs/customizing.md`.

---

## Project fingerprinting

The fingerprint detector runs at session start to bias model selection before any prompts are scored. It checks (in priority order):

1. `.mkproj` present and bash-heavy (3+ of: `#!/bin/bash`, function declarations, `if [`, `case...in`, `for...in`) → **Opus**
2. `requirements.txt` lists data science packages (numpy, pandas, torch, sklearn, tensorflow, etc.) → **Sonnet**
3. No source files found (`.py`, `.js`, `.ts`, `.go`, `.rs`, `.java`, etc.) but markdown/rst docs exist → **Haiku**

If none match, the `default_model` from config applies.

### What is a `.mkproj` file?

A `.mkproj` file is a machine-generated project manifest created by project-bootstrap, a companion scaffolding tool. When you run project-bootstrap to initialize a new project, it writes a `.mkproj` file at the root that records the project structure, intended tech stack, and shell script patterns.

arkitekton reads that file at session start to bias model selection. A bash-heavy `.mkproj` -- one that includes patterns like function declarations, conditionals, and loops -- signals infrastructure or scripting work, so arkitekton defaults to Opus without waiting for prompt analysis.

**You do not need project-bootstrap to use arkitekton.** If no `.mkproj` file is present, the fingerprint step is skipped and model selection falls through to the prompt complexity classifier and your configured `default_model`. Everything works; you just lose one early signal.

> **Note:** project-bootstrap is under active development as of November 2026 and has not been publicly released. This section will be updated with a link when it ships.

---

## How the classifier works

The heuristic scorer examines only the first 800 characters of each prompt (pasted logs and file contents shouldn't drag up the score). It applies three signals:

- **Length**: prompts over ~1,600 characters push the score up; under ~320 characters push it down
- **Heavy vocabulary**: architecture, refactor, review, audit, debug, investigate, root cause, security, exploit → each distinct match raises the score by 0.12
- **Light vocabulary**: rename, typo, format, list, show me, run tests, single file, one line, commit message → each distinct match lowers the score by 0.12

The score is clamped to [0.0, 1.0]. Below `thresholds.light` (default 0.30) -> Haiku. Above `thresholds.heavy` (default 0.65) -> Opus. In between -> Sonnet.

No LLM calls. No network. Runs in under 50 ms.

---

## Architecture

```
~/bin/claude  (wrapper)
    │
    ├── advisor session-start  →  picks model, launches claude --model <tier>
    │
    ├── UserPromptSubmit hook  →  scores each prompt, injects nudge if mismatched
    │
    ├── Stop hook              →  counts turns from transcript, appends to cost journal
    │
    └── advisor run            →  orchestrator decomposes goal, runner dispatches workers
```

Source layout:

```
src/architekton/
  advisor.py       CLI entry point (classify, session-start, warn, run, report, toggle, status)
  classifier.py    Heuristic prompt scorer
  config.py        Config loading and resolution (global + project merge)
  fingerprint.py   Project-type detector
  journal.py       Cost journal: append, count turns, generate report
  orchestrator.py  Decomposes a goal into tasks via an LLM call
  runner.py        Parallel task executor with live ANSI TUI
  hooks/           Shell hooks installed by scripts/install.sh

src/mod/
  architekton-warn/   Claude Code mod plugin (loads the warn hook into the editor)
  marketplace.json

config/
  schema.json          Config schema (validation + TUI field definitions)
  .defaults/
    global.json        Factory defaults (read-only reference)
    project.json       Project-level factory defaults
```

---

## Developer scripts

Five scripts at the project root cover the full contributor workflow. None of them start a background process -- each one runs, prints results, and exits.

| Script | What it does |
|---|---|
| `dev-install.sh` | Creates `.venv` and installs architekton in editable mode. Run once after cloning, and again when `pyproject.toml` changes. |
| `dev-uninstall.sh` | Removes `.venv`, build artifacts, and compiled bytecode. Reverses `dev-install.sh`. Does **not** uninstall architekton from your system -- use `scripts/uninstall.sh` for that. |
| `dev-run.sh` | Prints the current architekton config and detected session model, then exits. One-shot status check only -- there is no persistent process, so there is no stop command. |
| `dev-test.sh` | Runs the full test suite (145 tests, stdlib only, no network). |
| `dev-configure.sh` | Opens the interactive TUI config editor using the dev environment (runs from source). For post-install use, run `architekton-configure` instead -- that uses the installed package. |

To install or remove architekton from your system, use the scripts in `scripts/`:

```bash
bash scripts/install.sh     # install
bash scripts/uninstall.sh   # remove
```

---

## Requirements

- Python 3.9+
- Claude Code (the `claude` CLI)
- `jq` (used by the wrapper shell script)
- Bash

No third-party Python packages in the hot path. The classifier and all session hooks run on stdlib alone.

---

## About the name

*architekton* (ἀρχιτέκτων) is the ancient Greek word for master builder -- from *archi* (chief, leader) and *tekton* (craftsman, builder). It is the direct ancestor of the English word "architect."

![daedalus2](README_images/daedalus2.png)

<div align="center">*A Roman mosaic from Zeugma, Commagene (now in the Zeugma Mosaic Museum) depicting Daedalus and his son Icarus.*</div>

The word described the person who oversaw construction: not the one swinging a hammer, but the one who understood the whole structure, assigned the right craftsmen to the right work, and kept everything coherent as the parts came together. That is exactly what this tool does. The Opus orchestrator understands the goal and lays out the work. The Haiku workers execute their assigned pieces in parallel. Neither one could do the other's job as well.

The word appears in that sense as far back as Paul's first letter to the Corinthians (3:10), where he describes laying a foundation as a *sophos architekton* -- a skilled master builder. It has been in use for the same meaning for roughly two thousand years.

If you search GitHub you will find several repositories using the name or close variations of it, most of them focused on software architecture tooling. The connection is intuitive enough that people keep arriving at it independently.

---

## Built with

[Claude Code](https://claude.ai/code) -- Anthropic's AI coding assistant -- was used throughout the development of this project for design, implementation, testing, and documentation.

---

## License

MIT. Keep the copyright notice, do what you want.
