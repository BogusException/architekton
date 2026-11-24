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
2. Create the venv: `python -m venv .venv && source .venv/bin/activate`
3. Install development dependencies: `pip install -r requirements.txt`
4. Run the installer: `bash scripts/install.sh`

The installer is idempotent. Running it again on an already-installed system is safe -- it skips steps that are already in place.

## 3. Verifying the install

```bash
# Confirm the wrapper is in place
which claude   # should show ~/bin/claude

# Check current config and detected model
PYTHONPATH=src python -m architekton.advisor status

# Run the full test suite
bash dev-test.sh   # all 37 tests should pass
```

If `advisor status` prints `state: enabled` and a model source, the install succeeded.
