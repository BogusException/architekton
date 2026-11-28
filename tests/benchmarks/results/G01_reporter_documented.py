"""
Formats a ValidationReport into human-readable text or JSON for
output to stdout or a file. Supports plain text and JSON output modes.
"""

import json
import sys
from pathlib import Path

from validator import ValidationReport


def _text_lines(report: ValidationReport) -> list[str]:
    """Build the lines of a plain text validation report.

    Args:
        report: The validation report to format.

    Returns:
        list[str]: Report lines without line terminators. The failure
        section is appended only when the report did not pass.
    """
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
    """Format a validation report as plain text.

    Args:
        report: The validation report to format.

    Returns:
        str: The report lines joined with newline characters.
    """
    return "\n".join(_text_lines(report))


def to_json(report: ValidationReport) -> str:
    """Serialize a validation report to an indented JSON string.

    Args:
        report: The validation report to serialize.

    Returns:
        str: A JSON object with the keys passed, total, pass_count,
        fail_count, and records, indented by two spaces. Each entry in
        records has the keys id, passed, and failures.

    Raises:
        TypeError: If a value in the report, such as a record ID or a
            failure message, cannot be serialized by json.dumps.
        ValueError: If the report contains a circular reference.
    """
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
    """Write a validation report to a file or to stdout.

    Args:
        report: The validation report to write.
        fmt: Output format. "json" selects JSON output. Any other value
            selects plain text.
        dest: Path of the output file. If None or empty, the report is printed
            to stdout.

    Raises:
        OSError: If dest cannot be written.
        TypeError: If the format is "json" and a report value cannot be
            serialized by json.dumps.
        ValueError: If the format is "json" and the report contains a circular
            reference.
    """
    content = to_json(report) if fmt == "json" else to_text(report)
    if dest:
        Path(dest).write_text(content)
    else:
        print(content, file=sys.stdout)
