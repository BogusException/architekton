# Portable install plan

Goal: someone with no knowledge of the author's machines can run `git clone`, run one installer, and have architekton working. The author proves this by installing from GitHub on a clean client machine, then running Claude Code from there.

Status as of 2026-11-26: not ready. The code has no hardcoded personal paths (audited), but nothing has been tested from a fresh clone.

## Decisions to confirm

1. **Per-user install, not `/opt`.** The installer already writes to `~/.claude/architekton/`, `~/bin/claude` and `~/.claude/settings.json`. Those are per-user by nature, so `/opt` would add `sudo` and permission problems for no gain. The clone can live anywhere (for example `~/src/architekton`). Updating is `git pull` then re-run `scripts/install.sh`, which is safe to re-run.
2. **Test on a clean client, not on the dev server.** The dev server still has the older `smartmodel` / `auto-brain` hooks installed beside architekton, so it cannot show what a new user sees.
3. **Claude Code is run in the user's own project folders.** architekton is global (wrapper plus hooks). Running Claude inside the clone loads the repo's contributor `CLAUDE.md` and `.claude/`, which is only right for contributors (see item 5).

## Audit findings

Already fine:

- No `/home/<user>`, mount path or hostname hardcoded in tracked source, config or scripts.
- `.mkproj` and `.env` are not tracked. Only `.env.example` is.
- `scripts/install.sh` runs from `$REPO` (wherever the clone is), backs up before editing, refuses to overwrite a wrapper it does not own, and honours `CLAUDE_CONFIG_DIR` and `ARCHITEKTON_BIN_DIR`.
- Runtime needs only Python 3.9+ (stdlib), `jq` and the `claude` binary.
- A CI workflow exists (`.github/workflows/ci.yml`).

Gaps:

| # | Gap | Why it matters |
|---|---|---|
| 1 | Never installed from a fresh clone | Every other claim is unproven until this passes |
| 2 | Wrapper is not first on PATH on a stock install | Claude Code's own installer puts `claude` in `~/.local/bin`, which can precede `~/bin`. The wrapper then never runs. `install.sh` only warns |
| 3 | Aliases or scripts that call `claude` by full path bypass the wrapper | Looks like "installed but not working" |
| 4 | Claude Code's updater may rewrite `~/.local/bin/claude` | If the wrapper ever lives there, an update could remove it. Keep the wrapper in `~/bin` |
| 5 | Contributor files ship to every clone: `CLAUDE.md`, `AGENTS.md`, 16 files under `.claude/` | Hooks and response-format rules written for the author's workflow would apply to anyone running Claude inside the clone |
| 6 | `core.hooksPath` is local git config, so a fresh clone has no private-path guard | Contributors can commit private files. Needs a setup step |
| 7 | `docs/install.md` is written around the dev scripts | A user needs a "clone and install" page, with dev setup separate |
| 8 | Smoke test for the mid-session warn hook is still open | The upstream blocker (anthropics/claude-code#111757) means the hook cannot read `CLAUDE_MODEL`. The wrapper exports `ARCHITEKTON_MODEL` instead. This must be verified on a fresh install |
| 9 | No version tag, no changelog | A public client needs something to install and a way to know what changed |
| 10 | The `tasks/todo.md` migration section names a private network address | Move it out of tracked files before the repo is pushed to GitHub |

## Work items, in order

Each item has an acceptance check.

1. **Clean-room install on the dev server, in a throwaway home.** Clone into an empty temp directory, then run `ARCHITEKTON_NONINTERACTIVE=1 CLAUDE_CONFIG_DIR=<tmp>/claude ARCHITEKTON_BIN_DIR=<tmp>/bin bash scripts/install.sh`. Check that `<tmp>/bin/claude`, `<tmp>/claude/architekton/` and the settings hooks appear, and that nothing outside `<tmp>` changed. Then run `scripts/uninstall.sh` and check the tree is back to empty.
2. **Fix whatever step 1 finds.** Repeat until it passes with no manual steps.
3. **PATH check in the installer (gap 2, 3, 4).** After install, print the exact line to add to the shell profile when `command -v claude` is not the wrapper. Say plainly that full-path aliases bypass it. Acceptance: a stock install on a machine with `claude` in `~/.local/bin` prints a working fix, and applying it makes `command -v claude` return the wrapper.
4. **Contributor setup script (gap 6).** Add one step, run by `dev-install.sh`, that sets `core.hooksPath .githooks`. Acceptance: a fresh clone plus `dev-install.sh` blocks a commit of a private path.
5. **Separate contributor files from the product (gap 5).** Decide between two options. Option A: keep them, and label them contributor-only at the top of each. Option B: move the author's personal rules out of the repo and keep only what a contributor needs. Recommended: B for anything about response format or the `responses/` archive, A for the rest.
6. **User-facing install page (gap 7).** Rewrite `docs/install.md` as: prerequisites (Ubuntu `apt` line), clone, `bash scripts/install.sh`, PATH step, verify, update, uninstall. Move dev setup to `docs/contributing.md`. Acceptance: someone follows it on a clean machine with no other help.
7. **Smoke-test the warn hook (gap 8).** On the clean client, start a session and send a prompt whose complexity does not match the session model. Check that the one-line warning appears and that the journal gets an entry at session end.
8. **CI on a clean runner.** Check `ci.yml` passes with no `.venv` and no `~/.claude`. Add an install-and-uninstall job that repeats step 1.
9. **Move private notes out of tracked files (gap 10).**
10. **Release.** Set the version in one place, tag `v0.1.0`, add a short changelog, publish the GitHub release.
11. **Client install from GitHub.** On the client machine: clone from GitHub, follow `docs/install.md` exactly, run Claude Code in a normal project folder, and confirm the wrapper picks a model, the hook warns, and the journal records the session. Any step that needs knowledge outside the docs is a bug to fix and repeat.

## Definition of done

A person who has only the GitHub URL and the install page can install, use, update and uninstall architekton on a clean Ubuntu machine, with no step that depends on the author's machines, mounts or accounts.
