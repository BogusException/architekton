"""
Formats a ValidationReport into human-readable text or JSON for
output to stdout or a file. Supports plain text and JSON output modes.
"""

import json
import sys
from pathlib import Path

from validator import ValidationReport


def _text_lines(report: ValidationReport) -> list[str]:
    lines = [
        f"Validation {'PASSED' if report.ok else 'FAILED'}",
        f"  Total records : {report.total}",
        f"  Passed        : {report.passed}",
        f"  Failed        : {report.failed}",
    ]
    if not report.ok:
        lines.append("")
        lines.append("Failures:")
        for result in report.results:
            if not result.passed:
                lines.append(f"  Record {result.record_id}:")
                for msg in result.failures:
                    lines.append(f"    - {msg}")
    return lines


def to_text(report: ValidationReport) -> str:
    return "\n".join(_text_lines(report))


def to_json(report: ValidationReport) -> str:
    data = {
        "passed": report.ok,
        "total": report.total,
        "pass_count": report.passed,
        "fail_count": report.failed,
        "records": [
            {
                "id": r.record_id,
                "passed": r.passed,
                "failures": r.failures,
            }
            for r in report.results
        ],
    }
    return json.dumps(data, indent=2)


def write(report: ValidationReport, fmt: str = "text", dest: str | None = None):
    """Write report to dest file (or stdout if dest is None)."""
    content = to_json(report) if fmt == "json" else to_text(report)
    if dest:
        Path(dest).write_text(content)
    else:
        print(content, file=sys.stdout)
