# Install

For development setup, see [contributing.md](contributing.md).

## Prerequisites

- **Python 3.9+** -- `python3 --version` to confirm
- **Claude Code** -- `npm install -g @anthropic-ai/claude-code`
- **jq** -- `sudo apt install jq` on Ubuntu/Debian, `brew install jq` on macOS

## Install

```bash
git clone https://github.com/theitguys/architekton.git
cd architekton
bash scripts/install.sh
```

The installer copies the package to `~/.claude/architekton/`, places the session wrapper at `~/bin/claude`, and registers the warn and cost journal hooks in `~/.claude/settings.json`.

If `~/bin` is not already in your PATH, the installer detects your shell profile and offers to add the line automatically. Answer `y` at the prompt, then reload:

```bash
source ~/.bashrc   # or ~/.zshrc on zsh
```

Confirm the wrapper is active:

```bash
which claude   # should show /home/<you>/bin/claude
```

## Configure

Run the interactive config editor once to review defaults:

```bash
architekton-configure
```

Arrow keys to navigate, type to edit, `s` to save, `q` to quit without saving. Settings land in `~/.claude/architekton/config.json`.

## Verify

```bash
architekton status
```

Prints the current config, detected session model, and recent journal entries.

## Update

```bash
cd architekton
git pull
bash scripts/install.sh
```

The installer is safe to re-run. It backs up any files it replaces.

## Uninstall

```bash
bash scripts/uninstall.sh
```

Removes the wrapper, hooks, skill, and installed package. Leaves `config.json` and `cost-journal.jsonl` (your data) intact. To remove those too:

```bash
bash scripts/uninstall.sh --purge
```
