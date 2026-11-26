#!/usr/bin/env python3
"""
architekton pre-flight checker.

Verifies that all prerequisites and Claude Code integration points are in
place before or after install. Exits 0 if everything passes, 1 if anything
fails, 2 on usage error.

Usage:
    python3 scripts/preflight.py              # pre-install prerequisites
    python3 scripts/preflight.py --post       # post-install verification
    python3 scripts/preflight.py --all        # both phases

Environment overrides (same as install.sh):
    CLAUDE_CONFIG_DIR     override ~/.claude
    ARCHITEKTON_BIN_DIR   override ~/bin
"""

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

_use_color = sys.stdout.isatty() and platform.system() != "Windows"

def _c(code, text):
    return f"\033[{code}m{text}\033[0m" if _use_color else text

def _ok(label, detail=""):
    suffix = f"  ({detail})" if detail else ""
    print(f"  {_c('32', 'OK     ')}  {label}{suffix}")

def _fail(label, fix=""):
    print(f"  {_c('31', 'MISSING')}  {label}")
    if fix:
        print(f"             {_c('33', 'fix:')} {fix}")

def _warn(label, detail=""):
    suffix = f"  ({detail})" if detail else ""
    print(f"  {_c('33', 'WARN   ')}  {label}{suffix}")

def _header(title):
    print(f"\n=== {title} ===")

_errors = 0
_warnings = 0

def _check(label, cond, fix="", detail="", warn_only=False):
    global _errors, _warnings
    if cond:
        _ok(label, detail)
        return True
    else:
        if warn_only:
            _warn(label, detail)
            _warnings += 1
        else:
            _fail(label, fix)
            _errors += 1
        return False

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

HOME        = Path.home()
CLAUDE_DIR  = Path(os.environ.get("CLAUDE_CONFIG_DIR", HOME / ".claude"))
BIN_DIR     = Path(os.environ.get("ARCHITEKTON_BIN_DIR", HOME / "bin"))
BRAIN_HOME  = CLAUDE_DIR / "architekton"
LIB_DIR     = BRAIN_HOME / "lib" / "architekton"
HOOK_DIR    = LIB_DIR / "hooks"
WRAPPER     = BIN_DIR / "claude"
CONFIGURE   = BIN_DIR / "architekton-configure"
SETTINGS    = CLAUDE_DIR / "settings.json"
CONFIG_FILE = BRAIN_HOME / "config.json"
SKILL_DIR   = CLAUDE_DIR / "skills" / "architekton"

WRAPPER_MARKER   = "architekton-wrapper"
HOOK_WARN        = HOOK_DIR / "architekton-warn.sh"
HOOK_JOURNAL     = HOOK_DIR / "cost-journal.sh"
HOOK_WRAPPER_SH  = HOOK_DIR / "claude-wrapper.sh"

REQUIRED_MODULES = [
    "advisor.py", "classifier.py", "config.py",
    "fingerprint.py", "journal.py", "orchestrator.py",
    "runner.py", "schema_validator.py", "tui.py",
]

# ---------------------------------------------------------------------------
# Phase 1: prerequisites
# ---------------------------------------------------------------------------

def phase_pre():
    _header("Prerequisites")

    # Python version
    major, minor = sys.version_info[:2]
    _check(
        f"Python {major}.{minor}",
        (major, minor) >= (3, 9),
        fix="Install Python 3.9 or later.",
        detail=sys.executable,
    )

    # jq
    jq = shutil.which("jq")
    _check(
        "jq",
        jq is not None,
        fix="sudo apt install jq   (Ubuntu)  |  brew install jq   (macOS)",
        detail=jq or "",
    )

    # Claude Code binary
    # Look for the real claude, not our wrapper. On a fresh machine the
    # wrapper does not exist yet, so command -v gives the upstream binary.
    claude_path = shutil.which("claude")
    if claude_path:
        try:
            with open(claude_path) as fh:
                is_wrapper = WRAPPER_MARKER in fh.read(512)
        except Exception:
            is_wrapper = False
        if is_wrapper:
            _warn(
                "claude on PATH is already the architekton wrapper",
                detail="run --post to verify the install instead",
            )
        else:
            _ok("claude", detail=claude_path)
    else:
        _fail(
            "claude (Claude Code)",
            fix="npm install -g @anthropic-ai/claude-code",
        )

    # git
    git = shutil.which("git")
    _check("git", git is not None, fix="sudo apt install git   (Ubuntu)  |  brew install git   (macOS)")

    # ~/bin writable (or will be created by installer)
    if BIN_DIR.exists():
        _check(
            f"{BIN_DIR} exists",
            os.access(BIN_DIR, os.W_OK),
            fix=f"chmod u+w {BIN_DIR}",
        )
    else:
        _check(
            f"{BIN_DIR} parent writable",
            os.access(BIN_DIR.parent, os.W_OK),
            fix=f"mkdir -p {BIN_DIR}",
        )

    # ~/bin on PATH
    path_dirs = [Path(p).expanduser().resolve() for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    bin_in_path = BIN_DIR.resolve() in path_dirs
    _check(
        f"{BIN_DIR} in PATH",
        bin_in_path,
        fix=f'export PATH="{BIN_DIR}:$PATH"  (add to ~/.bashrc or ~/.zshrc)',
        warn_only=True,
    )

    # Windows / WSL note
    if platform.system() == "Windows":
        _warn(
            "Running on Windows (native)",
            detail="architekton bash hooks require WSL2. See docs/windows.md.",
        )
    elif "microsoft" in platform.uname().release.lower():
        _ok("WSL environment detected", detail="bash hooks will work here")


# ---------------------------------------------------------------------------
# Phase 2: post-install verification
# ---------------------------------------------------------------------------

def phase_post():
    _header("Wrapper")

    if WRAPPER.exists() or WRAPPER.is_symlink():
        try:
            with open(WRAPPER) as fh:
                content = fh.read(1024)
            is_ours = WRAPPER_MARKER in content
        except Exception:
            is_ours = False
        _check(
            f"{WRAPPER} is architekton wrapper",
            is_ours,
            fix=f"Re-run scripts/install.sh. If another program owns {WRAPPER}, set ARCHITEKTON_BIN_DIR.",
        )
    else:
        _fail(
            f"{WRAPPER} not found",
            fix="Run scripts/install.sh",
        )
        _errors_bump()

    _check(
        f"{CONFIGURE} present",
        CONFIGURE.exists(),
        fix="Re-run scripts/install.sh",
    )

    _header("Installed package")

    _check(
        f"{LIB_DIR} present",
        LIB_DIR.is_dir(),
        fix="Run scripts/install.sh",
    )

    for mod in REQUIRED_MODULES:
        _check(
            mod,
            (LIB_DIR / mod).exists(),
            fix=f"Re-run scripts/install.sh (missing: {LIB_DIR / mod})",
        )

    for hook in [HOOK_WARN, HOOK_JOURNAL, HOOK_WRAPPER_SH]:
        exists = hook.exists()
        executable = os.access(hook, os.X_OK) if exists else False
        label = hook.name
        if _check(label + " exists", exists, fix="Re-run scripts/install.sh"):
            _check(label + " executable", executable, fix=f"chmod +x {hook}")

    _check(
        "config.json present",
        CONFIG_FILE.exists(),
        fix="Re-run scripts/install.sh",
    )

    _header("Python import smoke test")

    result = subprocess.run(
        [
            sys.executable, "-c",
            f"import sys; sys.path.insert(0, '{LIB_DIR.parent}'); "
            "import architekton.classifier; "
            "import architekton.config; "
            "import architekton.journal; "
            "print('ok')"
        ],
        capture_output=True, text=True,
    )
    _check(
        "architekton imports cleanly",
        result.returncode == 0 and result.stdout.strip() == "ok",
        fix=result.stderr.strip() or "Re-run scripts/install.sh",
        detail=result.stdout.strip() if result.returncode == 0 else "",
    )

    _header("Claude Code settings hooks")

    if not SETTINGS.exists():
        _fail(f"{SETTINGS} not found", fix="Run scripts/install.sh")
        global _errors
        _errors += 1
    else:
        try:
            with open(SETTINGS) as fh:
                cfg = json.load(fh)
        except json.JSONDecodeError as exc:
            _fail(f"{SETTINGS} is not valid JSON", fix=str(exc))
            _errors += 1
            cfg = {}

        # UserPromptSubmit -> architekton-warn.sh
        warn_registered = _hook_registered(cfg, "UserPromptSubmit", str(HOOK_WARN))
        _check(
            "UserPromptSubmit hook registered",
            warn_registered,
            fix="Re-run scripts/install.sh",
        )

        # Stop -> cost-journal.sh
        journal_registered = _hook_registered(cfg, "Stop", str(HOOK_JOURNAL))
        _check(
            "Stop hook (cost journal) registered",
            journal_registered,
            fix="Re-run scripts/install.sh",
        )

        # Verify hook paths exist on disk
        for event, hook_path in [
            ("UserPromptSubmit", HOOK_WARN),
            ("Stop", HOOK_JOURNAL),
        ]:
            if _hook_registered(cfg, event, str(hook_path)):
                _check(
                    f"hook path exists on disk: {hook_path.name}",
                    hook_path.exists(),
                    fix="Re-run scripts/install.sh",
                )

    _header("Skills")

    skill_md = SKILL_DIR / "SKILL.md"
    skill_sh = SKILL_DIR / "architekton.sh"
    if SKILL_DIR.exists():
        _check("/architekton skill SKILL.md", skill_md.exists(), fix="Re-run scripts/install.sh and choose Y for skill")
        _check("/architekton skill architekton.sh", skill_sh.exists(), fix="Re-run scripts/install.sh and choose Y for skill")
    else:
        _warn(
            "/architekton skill not installed",
            detail="optional -- re-run scripts/install.sh and choose Y to install",
        )

    _header("Mod (architekton-warn)")

    claude_bin = shutil.which("claude")
    if claude_bin:
        try:
            result = subprocess.run(
                ["claude", "plugin", "list"],
                capture_output=True, text=True, timeout=10,
            )
            if "architekton-warn" in result.stdout:
                _ok("architekton-warn mod installed")
            else:
                _warn(
                    "architekton-warn mod not listed by 'claude plugin list'",
                    detail="run: claude plugin install architekton-warn@architekton",
                )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            _warn("could not query mod status -- 'claude plugin list' timed out or failed")
    else:
        _warn("claude binary not found -- cannot verify mod status")


def _hook_registered(cfg, event, command):
    """Return True if command appears as a hook command under the given event."""
    try:
        for group in cfg.get("hooks", {}).get(event, []):
            for hook in group.get("hooks", []):
                if hook.get("command") == command:
                    return True
    except Exception:
        pass
    return False


def _errors_bump():
    global _errors
    _errors += 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    args = set(sys.argv[1:])
    if args - {"--pre", "--post", "--all"}:
        print(__doc__)
        sys.exit(2)

    run_pre  = "--pre"  in args or "--all" in args or not args
    run_post = "--post" in args or "--all" in args

    print(f"architekton pre-flight  (Python {sys.version.split()[0]}, {platform.system()})")
    print(f"  CLAUDE_DIR : {CLAUDE_DIR}")
    print(f"  BIN_DIR    : {BIN_DIR}")

    if run_pre:
        phase_pre()

    if run_post:
        phase_post()

    print()
    if _errors:
        print(_c("31", f"FAILED: {_errors} check(s) did not pass."))
        sys.exit(1)
    elif _warnings:
        print(_c("33", f"PASSED with {_warnings} warning(s)."))
    else:
        print(_c("32", "All checks passed."))


if __name__ == "__main__":
    main()
