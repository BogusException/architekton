# Windows compatibility notes

## Status

architekton's bash hooks do not run on native Windows. WSL2 is required.

The `scripts/preflight.py` script runs on native Windows (Python is cross-platform), and it will tell you if the WSL requirement is unmet. Everything else -- install, configure, and daily use -- must happen inside a WSL2 terminal.

## Requirements

- Windows 10 version 2004 or later (WSL2 support)
- WSL2 with a Linux distribution (Ubuntu 22.04 or 24.04 recommended)
- Claude Code installed inside WSL, not on the Windows side
- Python 3.9+, jq, and git inside WSL

## Install Claude Code inside WSL

Open a WSL2 terminal (not PowerShell, not CMD):

```bash
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt install -y nodejs
npm install -g @anthropic-ai/claude-code
```

Confirm the binary is in the WSL environment:

```bash
which claude   # should show /home/<you>/.npm-global/bin/claude or similar
claude --version
```

## Install architekton inside WSL

Same as the Linux install -- everything runs in the WSL shell:

```bash
git clone https://github.com/BogusException/architekton.git
cd architekton
bash scripts/install.sh
```

The installer creates `~/bin/claude` (the wrapper) and registers hooks in `~/.claude/settings.json` -- all inside the WSL filesystem.

## PATH in WSL

Ubuntu under WSL adds `~/bin` to PATH automatically if the directory exists. After install:

```bash
source ~/.bashrc
which claude   # should show /home/<you>/bin/claude
```

If `which claude` still shows the npm path, add this to `~/.bashrc`:

```bash
export PATH="$HOME/bin:$PATH"
```

## Running Claude Code on Windows

Launch it from a WSL2 terminal, not from Windows Explorer or PowerShell:

```bash
cd ~/your-project
claude
```

The hooks (wrapper, architekton-warn, cost-journal) are bash scripts. They need a bash environment to run. Opening Claude Code from a Windows shortcut or via `wsl -e claude` without an interactive session may prevent hooks from firing correctly.

## Pre-flight check from PowerShell

The preflight script runs on native Windows if you have Python installed there, but it can only check Python prerequisites. Install verification (wrapper, hooks, settings.json) requires running inside WSL where `~/.claude` and `~/bin` live:

```powershell
# From PowerShell -- prerequisite check only, not install verification
python scripts\preflight.py
```

```bash
# From WSL -- full check including post-install
python3 scripts/preflight.py --all
```

## Known issues

- The architekton-warn mod (`architekton-warn.sh`) hooks into Claude Code's `UserPromptSubmit` event. This fires correctly in a WSL session. It does not fire when Claude Code is opened from a Windows GUI launcher that does not inherit the WSL shell environment.
- `architekton-configure` requires a terminal with ANSI color support. The Windows Terminal app (WSL profile) works correctly. CMD and older PowerShell windows may display raw escape codes.
- The `cost-journal.sh` Stop hook writes to `~/.claude/architekton/cost-journal.jsonl` inside WSL. This file is accessible from Windows at `\\wsl$\Ubuntu\home\<user>\.claude\architekton\cost-journal.jsonl` if you need to open it in a Windows editor.

## Upstream blocker

anthropics/claude-code#111757 -- `UserPromptSubmit` hooks do not receive `CLAUDE_MODEL` in subprocess environments. This affects the warn hook on all platforms, not only Windows. The wrapper exports `ARCHITEKTON_MODEL` as a workaround. See CHANGELOG.md for details.
