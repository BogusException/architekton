"""Project-type detector: reads project files to bias model selection."""

import re
from pathlib import Path

DATA_SCIENCE_PACKAGES = frozenset([
    "altair", "bokeh", "dask", "ipython", "jupyter", "keras",
    "lightgbm", "matplotlib", "notebook", "numpy", "pandas", "plotly",
    "pyspark", "scikit-learn", "scipy", "seaborn", "sklearn", "statsmodels",
    "tensorflow", "torch", "xgboost",
])

_BASH_PATTERNS = [
    re.compile(r'#!/bin/bash'),
    re.compile(r'#!/usr/bin/env\s+bash'),
    re.compile(r'\bfunction\s+\w+\s*\('),
    re.compile(r'\bif\s+\['),
    re.compile(r'\bcase\s+\S+\s+in\b'),
    re.compile(r'\bfor\s+\w+\s+in\b'),
]
_BASH_HEAVY_THRESHOLD = 3

_CODE_EXTENSIONS = frozenset([
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".go", ".rs", ".java", ".rb", ".cpp", ".c", ".cs", ".php",
])


def _read_text(path):
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _parse_requirement(line):
    """Extract package name from a requirements.txt line."""
    line = line.strip()
    if not line or line.startswith("#") or line.startswith("-"):
        return None
    return re.split(r'[>=<![\s;]', line)[0].strip().lower()


def _has_code_files(project_dir):
    for path in project_dir.rglob("*"):
        if path.suffix not in _CODE_EXTENSIONS:
            continue
        parts = path.relative_to(project_dir).parts
        if not any(p.startswith(".") for p in parts) and "node_modules" not in parts:
            return True
    return False


def detect(project_dir=None):
    """Scan project files and return {"tier": tier_or_None, "reason": str}.

    Rules (in priority order):
      1. .mkproj present and bash-heavy -> opus
      2. data science packages in requirements.txt -> sonnet
      3. docs-only, no source code -> haiku
    """
    if project_dir is None:
        from auto_brain.config import get_project_dir
        project_dir = get_project_dir()
    project_dir = Path(project_dir)

    content = _read_text(project_dir / ".mkproj")
    if content is not None:
        hits = sum(1 for p in _BASH_PATTERNS if p.search(content))
        if hits >= _BASH_HEAVY_THRESHOLD:
            return {"tier": "opus", "reason": "bash-heavy .mkproj"}

    req_text = _read_text(project_dir / "requirements.txt")
    if req_text is not None:
        packages = {_parse_requirement(line) for line in req_text.splitlines()} - {None}
        matched = packages & DATA_SCIENCE_PACKAGES
        if matched:
            sample = ", ".join(sorted(matched)[:3])
            return {"tier": "sonnet", "reason": f"data science packages ({sample})"}

    if not _has_code_files(project_dir):
        doc_files = list(project_dir.rglob("*.md")) + list(project_dir.rglob("*.rst"))
        if doc_files:
            return {"tier": "haiku", "reason": "docs-only project"}

    return {"tier": None, "reason": "no fingerprint matched"}
