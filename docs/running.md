# Running

## 1. Quick start

After install, `claude` just works. The wrapper is transparent -- every session start automatically picks the right model based on the project and prints a one-line advisory:

```
[architekton] Starting with sonnet (project-fingerprint (data science packages (numpy, pandas)))
```

## 2. Common tasks

| Task | Command |
|------|---------|
| Run tests | `bash test.sh` |
| Run tests with output | `PYTHONPATH=src python -m unittest discover -s tests -v` |
| Check current config | `PYTHONPATH=src python -m architekton.advisor status` |
| Score a prompt | `echo "your prompt" \| PYTHONPATH=src python -m architekton.advisor classify` |
| Disable architekton | `PYTHONPATH=src python -m architekton.advisor toggle off` |
| Re-enable | `PYTHONPATH=src python -m architekton.advisor toggle on` |
| Bypass for one session | `ARCHITEKTON_DISABLE=1 claude` |
| Spend report (last 7 days) | `PYTHONPATH=src python -m architekton.advisor report --days 7` |
| Spend report (all time) | `PYTHONPATH=src python -m architekton.advisor report` |
| Run a multi-agent job | `PYTHONPATH=src python -m architekton.advisor run "describe the goal"` |

## 3. Environment modes

This project has no staging or production deployment. It runs identically on every machine after `install.sh`. Config is per-user (`~/.claude/architekton/config.json`) and per-project (`.claude/architekton.json`).

The only runtime distinction is `ARCHITEKTON_DISABLE=1`, which bypasses architekton for a single session without changing any config.
