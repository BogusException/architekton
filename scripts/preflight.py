#!/usr/bin/env python3
"""
architekton pre-flight checker.

Verifies that all prerequisites and Claude Code integration points are in
place before or after install. Exits 0 if everything passes, 1 if anything
fails, 2 on usage error.

Usage:
    python3 scripts/preflight.py              # pre-install prerequisites
    python3 scripts/preflight.py --post       # post-install verification
    python3 scripts/preflight.py --detect     # describe whatever is currently installed (no pass/fail)
    python3 scripts/preflight.py --all        # pre + post

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

def _info(label, detail=""):
    suffix = f"  ({detail})" if detail else ""
    print(f"  {_c('36', 'INFO   ')}  {label}{suffix}")

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

WRAPPER_MARKER      = "architekton-wrapper"
AUTO_BRAIN_MARKER   = "auto-brain-wrapper"
HOOK_WARN           = HOOK_DIR / "architekton-warn.sh"
HOOK_JOURNAL        = HOOK_DIR / "cost-journal.sh"
HOOK_WRAPPER_SH     = HOOK_DIR / "claude-wrapper.sh"

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

    major, minor = sys.version_info[:2]
    _check(
        f"Python {major}.{minor}",
        (major, minor) >= (3, 9),
        fix="Install Python 3.9 or later.",
        detail=sys.executable,
    )

    jq = shutil.which("jq")
    _check(
        "jq",
        jq is not None,
        fix="sudo apt install jq   (Ubuntu)  |  brew install jq   (macOS)",
        detail=jq or "",
    )

    claude_path = shutil.which("claude")
    if claude_path:
        try:
            with open(claude_path) as fh:
                head = fh.read(512)
            is_wrapper = WRAPPER_MARKER in head or AUTO_BRAIN_MARKER in head
        except Exception:
            is_wrapper = False
        if is_wrapper:
            _warn(
                "claude on PATH is already a wrapper",
                detail="run --detect to describe the current install state",
            )
        else:
            _ok("claude", detail=claude_path)
    else:
        _fail(
            "claude (Claude Code)",
            fix="npm install -g @anthropic-ai/claude-code",
        )

    git = shutil.which("git")
    _check("git", git is not None,
           fix="sudo apt install git   (Ubuntu)  |  brew install git   (macOS)")

    if BIN_DIR.exists():
        _check(f"{BIN_DIR} exists", os.access(BIN_DIR, os.W_OK),
               fix=f"chmod u+w {BIN_DIR}")
    else:
        _check(f"{BIN_DIR} parent writable", os.access(BIN_DIR.parent, os.W_OK),
               fix=f"mkdir -p {BIN_DIR}")

    path_dirs = [Path(p).expanduser().resolve()
                 for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    _check(
        f"{BIN_DIR} in PATH",
        BIN_DIR.resolve() in path_dirs,
        fix=f'export PATH="{BIN_DIR}:$PATH"  (add to ~/.bashrc or ~/.zshrc)',
        warn_only=True,
    )

    if platform.system() == "Windows":
        _warn("Running on Windows (native)",
              detail="architekton bash hooks require WSL2. See docs/windows.md.")
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
            fix=(f"Re-run scripts/install.sh. "
                 f"If another program owns {WRAPPER}, set ARCHITEKTON_BIN_DIR "
                 f"or use scripts/install.sh --force to overwrite it."),
        )
    else:
        _fail(f"{WRAPPER} not found", fix="Run scripts/install.sh")
        global _errors
        _errors += 1

    _check(f"{CONFIGURE} present", CONFIGURE.exists(),
           fix="Re-run scripts/install.sh")

    _header("Installed package")

    _check(f"{LIB_DIR} present", LIB_DIR.is_dir(),
           fix="Run scripts/install.sh")

    for mod in REQUIRED_MODULES:
        _check(mod, (LIB_DIR / mod).exists(),
               fix=f"Re-run scripts/install.sh (missing: {LIB_DIR / mod})")

    for hook in [HOOK_WARN, HOOK_JOURNAL, HOOK_WRAPPER_SH]:
        exists = hook.exists()
        executable = os.access(hook, os.X_OK) if exists else False
        if _check(hook.name + " exists", exists, fix="Re-run scripts/install.sh"):
            _check(hook.name + " executable", executable,
                   fix=f"chmod +x {hook}")

    _check("config.json present", CONFIG_FILE.exists(),
           fix="Re-run scripts/install.sh")

    _header("Python import smoke test")

    result = subprocess.run(
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0, '{LIB_DIR.parent}'); "
         "import architekton.classifier; "
         "import architekton.config; "
         "import architekton.journal; "
         "print('ok')"],
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
        _errors += 1
    else:
        try:
            with open(SETTINGS) as fh:
                cfg = json.load(fh)
        except json.JSONDecodeError as exc:
            _fail(f"{SETTINGS} is not valid JSON", fix=str(exc))
            _errors += 1
            cfg = {}

        warn_registered = _hook_registered(cfg, "UserPromptSubmit", str(HOOK_WARN))
        _check("UserPromptSubmit hook registered", warn_registered,
               fix="Re-run scripts/install.sh")

        journal_registered = _hook_registered(cfg, "Stop", str(HOOK_JOURNAL))
        _check("Stop hook (cost journal) registered", journal_registered,
               fix="Re-run scripts/install.sh")

        for event, hook_path in [("UserPromptSubmit", HOOK_WARN), ("Stop", HOOK_JOURNAL)]:
            if _hook_registered(cfg, event, str(hook_path)):
                _check(f"hook path exists on disk: {hook_path.name}",
                       hook_path.exists(), fix="Re-run scripts/install.sh")

    _header("Skills")

    if SKILL_DIR.exists():
        _check("/architekton skill SKILL.md", (SKILL_DIR / "SKILL.md").exists(),
               fix="Re-run scripts/install.sh and choose Y for skill")
        _check("/architekton skill architekton.sh", (SKILL_DIR / "architekton.sh").exists(),
               fix="Re-run scripts/install.sh and choose Y for skill")
    else:
        _warn("/architekton skill not installed",
              detail="optional -- re-run scripts/install.sh and choose Y to install")

    _header("Mod (architekton-warn)")

    _check_mod()


# ---------------------------------------------------------------------------
# Phase 3: detect -- describe whatever is installed, no pass/fail
# ---------------------------------------------------------------------------

def phase_detect():
    _header("Wrapper detection")

    if WRAPPER.exists() or WRAPPER.is_symlink():
        try:
            with open(WRAPPER) as fh:
                head = fh.read(1024)
        except Exception:
            head = ""

        if WRAPPER_MARKER in head:
            _info(f"{WRAPPER}", "architekton wrapper")
        elif AUTO_BRAIN_MARKER in head:
            _info(f"{WRAPPER}", "auto-brain wrapper (predecessor -- install.sh will upgrade it)")
        elif WRAPPER.is_symlink():
            target = WRAPPER.resolve()
            _info(f"{WRAPPER}", f"symlink -> {target}  (install.sh will refuse unless you use --force)")
        elif head:
            first_line = head.splitlines()[0] if head.splitlines() else "(unreadable)"
            _warn(f"{WRAPPER}", f"unknown binary: {first_line}  -- install.sh will refuse; use --force or move it")
        else:
            _warn(f"{WRAPPER}", "unreadable file")
    else:
        _info(f"{WRAPPER}", "not present  (fresh install)")

    # Other claude binaries on PATH
    _header("Claude Code on PATH")

    path_dirs = os.environ.get("PATH", "").split(os.pathsep)
    found = []
    for d in path_dirs:
        p = Path(d) / "claude"
        if p.exists() and p != WRAPPER:
            try:
                with open(p) as fh:
                    head = fh.read(256)
                label = "wrapper" if (WRAPPER_MARKER in head or AUTO_BRAIN_MARKER in head) else "upstream binary"
            except Exception:
                label = "upstream binary"
            found.append((p, label))
    if found:
        for p, label in found:
            _info(str(p), label)
    else:
        _info("no other claude binaries found on PATH")

    _header("Installed package")

    if BRAIN_HOME.exists():
        _info(f"{BRAIN_HOME}", "present")
        if LIB_DIR.is_dir():
            modules = [m for m in REQUIRED_MODULES if (LIB_DIR / m).exists()]
            missing = [m for m in REQUIRED_MODULES if not (LIB_DIR / m).exists()]
            _info(f"modules: {len(modules)}/{len(REQUIRED_MODULES)} present",
                  ("missing: " + ", ".join(missing)) if missing else "complete")
        else:
            _info(f"{LIB_DIR}", "absent -- package not installed")
        if CONFIG_FILE.exists():
            _info("config.json", "present")
        else:
            _info("config.json", "absent -- will be written on first install")
    else:
        _info(f"{BRAIN_HOME}", "absent -- not installed")

    _header("Claude Code settings.json")

    if SETTINGS.exists():
        try:
            with open(SETTINGS) as fh:
                cfg = json.load(fh)
            hooks_section = cfg.get("hooks", {})
            if hooks_section:
                for event, groups in hooks_section.items():
                    cmds = []
                    for group in groups:
                        for hook in group.get("hooks", []):
                            cmd = hook.get("command", "")
                            if cmd:
                                cmds.append(Path(cmd).name)
                    if cmds:
                        _info(f"{event}", ", ".join(cmds))
            else:
                _info(f"{SETTINGS}", "no hooks registered")
        except json.JSONDecodeError:
            _warn(f"{SETTINGS}", "invalid JSON -- install.sh will refuse")
    else:
        _info(f"{SETTINGS}", "absent -- will be created on install")

    _header("Skills")

    skills_dir = CLAUDE_DIR / "skills"
    if skills_dir.exists():
        installed = sorted(p.name for p in skills_dir.iterdir() if p.is_dir())
        for s in installed:
            tag = "  <-- architekton" if s == "architekton" else ""
            _info(s, tag.strip() if tag.strip() else "")
    else:
        _info("~/.claude/skills/", "absent")

    _header("Mod (architekton-warn)")

    _check_mod(detect_mode=True)

    _header("Claude Code version")

    for binary in ["claude"]:
        b = shutil.which(binary)
        if b:
            try:
                r = subprocess.run([b, "--version"], capture_output=True, text=True, timeout=5)
                _info(b, r.stdout.strip() or r.stderr.strip())
            except Exception:
                _info(b, "version check failed")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _check_mod(detect_mode=False):
    claude_bin = shutil.which("claude")
    if claude_bin:
        try:
            result = subprocess.run(
                ["claude", "plugin", "list"],
                capture_output=True, text=True, timeout=10,
            )
            if "architekton-warn" in result.stdout:
                if detect_mode:
                    _info("architekton-warn mod", "installed")
                else:
                    _ok("architekton-warn mod installed")
            else:
                if detect_mode:
                    _info("architekton-warn mod", "not installed")
                else:
                    _warn("architekton-warn mod not listed by 'claude plugin list'",
                          detail="run: claude plugin install architekton-warn@architekton")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            _warn("could not query mod status -- 'claude plugin list' timed out or failed")
    else:
        _warn("claude binary not found -- cannot check mod status")


def _hook_registered(cfg, event, command):
    try:
        for group in cfg.get("hooks", {}).get(event, []):
            for hook in group.get("hooks", []):
                if hook.get("command") == command:
                    return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    args = set(sys.argv[1:])
    valid = {"--pre", "--post", "--detect", "--all"}
    if args - valid:
        print(__doc__)
        sys.exit(2)

    run_pre    = "--pre"    in args or "--all" in args or not args
    run_post   = "--post"   in args or "--all" in args
    run_detect = "--detect" in args

    print(f"architekton pre-flight  (Python {sys.version.split()[0]}, {platform.system()})")
    print(f"  CLAUDE_DIR : {CLAUDE_DIR}")
    print(f"  BIN_DIR    : {BIN_DIR}")

    if run_detect:
        phase_detect()
        print()
        print("Detection complete. No pass/fail -- use --post for a formal install check.")
        return

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
