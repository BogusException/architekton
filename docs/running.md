# Running

## 1. Quick start

After install, `claude` just works. The wrapper is transparent -- every session start automatically picks the right model based on the project and prints a one-line advisory:

```
[auto-brain] Starting with sonnet (project-fingerprint (data science packages (numpy, pandas)))
```

## 2. Common tasks

| Task | Command |
|------|---------|
| Run tests | `bash test.sh` |
| Run tests with output | `PYTHONPATH=src python -m unittest discover -s tests -v` |
| Check current config | `PYTHONPATH=src python -m auto_brain.advisor status` |
| Score a prompt | `echo "your prompt" \| PYTHONPATH=src python -m auto_brain.advisor classify` |
| Disable auto-brain | `PYTHONPATH=src python -m auto_brain.advisor toggle off` |
| Re-enable | `PYTHONPATH=src python -m auto_brain.advisor toggle on` |
| Bypass for one session | `SMARTMODEL_DISABLE=1 claude` |
| Spend report (last 7 days) | `PYTHONPATH=src python -m auto_brain.advisor report --days 7` |
| Spend report (all time) | `PYTHONPATH=src python -m auto_brain.advisor report` |
| Run a multi-agent job | `PYTHONPATH=src python -m auto_brain.advisor run "describe the goal"` |

## 3. Environment modes

This project has no staging or production deployment. It runs identically on every machine after `install.sh`. Config is per-user (`~/.claude/smartmodel/config.json`) and per-project (`.claude/smartmodel.json`).

The only runtime distinction is `SMARTMODEL_DISABLE=1`, which bypasses auto-brain for a single session without changing any config.
