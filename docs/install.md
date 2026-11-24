# Install

*This doc covers initial setup and re-setup after a fresh clone.*

## 1. Prerequisites

- Python 3.9+
- Claude Code installed and on your `PATH` (the real `claude` binary, not the wrapper)
- `jq` -- used by `scripts/install.sh` to edit `~/.claude/settings.json`
- `~/bin` on your `PATH` before the system `claude` binary (the installer places the wrapper there)

Verify PATH order: `which claude` should resolve to `~/bin/claude` after install. If it doesn't, add `export PATH="$HOME/bin:$PATH"` to your shell profile.

## 2. Setup

1. Clone the repo: `git clone <repo-url> && cd architekton`
2. Set up the dev environment: `bash dev-install.sh`
3. Install architekton on your system: `bash scripts/install.sh`

Both scripts are safe to re-run. `dev-install.sh` will announce if a venv already exists and skip recreating it. `scripts/install.sh` will announce "already installed -- reinstalling" and overwrite the previous install.

## 3. Configure architekton

The installer places `architekton-configure` on your PATH. Run it once to review the defaults and adjust anything you want:

```bash
architekton-configure
```

The editor shows every available setting with a short description. Use arrow keys to navigate, type to edit a value, and press `s` to save. Press `q` to exit without saving.

Your settings are written to `~/.claude/architekton/config.json`. You can re-run `architekton-configure` any time -- it never overwrites unsaved changes.

## 4. Verifying the install

```bash
# Confirm the wrapper is in place
which claude   # should show ~/bin/claude

# Check current config and detected session model
bash dev-run.sh

# Run the full test suite
bash dev-test.sh
```

If `dev-run.sh` prints `state: enabled` and a model source, the install succeeded.
