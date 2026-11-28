"""
Formats a ValidationReport into human-readable text or JSON for
output to stdout or a file. Supports plain text and JSON output modes.
"""

import json
import sys
from pathlib import Path

from validator import ValidationReport


def _text_lines(report: ValidationReport) -> list[str]:
    """Build the plain-text report as a list of lines.

    The first four lines are a summary. If the report has failures, a
    "Failures:" section follows with one entry per failed record.

    Args:
        report: The validation report to format.

    Returns:
        The report lines, without trailing newlines.
    """
    lines: list[str] = [
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
    """Format a validation report as plain text.

    Args:
        report: The validation report to format.

    Returns:
        The report as a newline-joined string with no trailing newline.
    """
    return "\n".join(_text_lines(report))


def to_json(report: ValidationReport) -> str:
    """Format a validation report as JSON.

    Args:
        report: The validation report to format.

    Returns:
        A JSON string, indented with two spaces. It has the keys "passed",
        "total", "pass_count", "fail_count" and "records". Each record has
        "id", "passed" and "failures".
    """
    data: dict[str, object] = {
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


def write(report: ValidationReport, fmt: str = "text", dest: str | None = None) -> None:
    """Write a report to a file, or to stdout if no file is given.

    Args:
        report: The validation report to write.
        fmt: Output format. "json" selects JSON. Any other value selects
            plain text.
        dest: Path of the file to write. If None or empty, the report is
            printed to stdout.

    Returns:
        None.

    Raises:
        OSError: If dest cannot be written (for example, the parent
            directory does not exist).
    """
    content = to_json(report) if fmt == "json" else to_text(report)
    if dest:
        Path(dest).write_text(content)
    else:
        print(content, file=sys.stdout)
