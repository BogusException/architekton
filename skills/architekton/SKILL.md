---
name: architekton
version: 1.0.0
description: "Model advisor and multi-agent job runner for Claude Code. /architekton run \"goal\" decomposes a natural-language goal into tasks and executes them in parallel with a live status display. Workers are assigned the right model tier per task (haiku for mechanical work, opus for complex reasoning). /architekton status shows active config and session model. /architekton report [--days N] shows per-project spend history."
argument-hint: "[run {goal} | status | report [--days N]]"
disable-model-invocation: true
---

# /architekton

## Step 1: Verify installation

Run this check first:

```bash
[ -f "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/architekton/lib/architekton/__init__.py" ] \
  && echo "installed" || echo "not_installed"
```

If the output is `not_installed`:

Tell the user:
> architekton is not installed. Run `bash install.sh` from the architekton repository, then try again.
> See docs/install.md for prerequisites (python3, jq, ~/bin in PATH).

Stop here.

## Step 2: Identify command

Parse the first word of `$ARGUMENTS` to determine which subcommand to run.

| User types | Subcommand |
|------------|------------|
| `/architekton run Build a REST API` | `run` |
| `/architekton status` | `status` |
| `/architekton report` | `report` |
| `/architekton report --days 7` | `report --days 7` |
| `/architekton` (no args) | show usage |

## Step 3: Run the command

Use `architekton.sh` from the installed skill directory. Strip ANSI codes from output before showing it in chat (the TUI uses color codes that do not render in text).

```bash
SKILL_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/architekton"
bash "$SKILL_DIR/architekton.sh" $ARGUMENTS 2>&1 \
  | sed 's/\x1B\[[0-9;]*[mGKHF]//g'
```

Replace `$ARGUMENTS` with the parsed subcommand and arguments from Step 2.

For `run`, the job description must be passed as a single quoted string:

```bash
bash "$SKILL_DIR/architekton.sh" run "Build a REST API for user authentication"
```

## Step 4: Interpret and display output

**`run`**: The final lines include a summary:
```
[architekton] Job done: N complete, N error, N skipped
  Output: ~/.claude/architekton/jobs/<timestamp>/
```
Show the summary and the output directory path. If there were errors, suggest checking the per-task `.txt` files in the output directory.

**`status`**: Show the output directly. It lists enabled/disabled state, mode, session model, and config file paths.

**`report`**: Show the output table. Each row is a project with model mix and estimated cost.

## Step 5: No arguments -- show usage

If `$ARGUMENTS` is empty or `help`, show:

```
/architekton run "goal"       — decompose goal into tasks, run in parallel
/architekton status           — show config and active session model
/architekton report           — spend report (all time)
/architekton report --days 7  — spend report (last 7 days)

Docs: docs/customizing.md (config), docs/running.md (commands)
```

## Notes

- Workers run with `ARCHITEKTON_DISABLE=1` so they do not recursively invoke architekton.
- Output for each task is saved to `~/.claude/architekton/jobs/<timestamp>/<task_id>.txt`.
- Thinking effort and timeout columns are visible in the TUI during live runs. When called through this skill, output is captured and shown after completion.
- To change orchestrator model for a single run: `/architekton run --orchestrator-model sonnet "goal"`
- Config files: `~/.claude/architekton/config.json` (global), `.claude/architekton.json` (project override).
