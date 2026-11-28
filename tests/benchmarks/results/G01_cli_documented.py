"""
Command-line entry point for the data processing pipeline. Accepts a
data file path, an optional list of transformation steps, and an output
format. Ties together data_loader, transformer, validator, and reporter.
"""

import argparse
import sys

from data_loader import load
from transformer import apply
from validator import validate
from reporter import write


DEFAULT_STEPS = ["strip_whitespace", "normalize_value", "add_flag"]
DEFAULT_RULES = ["has_id", "value_non_negative", "name_not_empty"]


def main():
    """Run the load, transform, validate, and report pipeline.

    Parses the command-line options, then loads the input file, applies the
    transformation steps, validates the records, and writes the report. The
    process exits with status 0 when the report is ok, 1 when it is not, and
    2 when a ValueError or FileNotFoundError is raised during the pipeline.

    Raises:
        SystemExit: Always raised by the final sys.exit call. argparse also
            raises it for invalid arguments or --help before the pipeline runs.
        OSError: Raised by load() or write() for file errors other than
            FileNotFoundError, such as PermissionError or IsADirectoryError.
            FileNotFoundError is caught and mapped to exit status 2.
    """
    parser = argparse.ArgumentParser(
        description="Load, transform, validate, and report on a data file.",
    )
    parser.add_argument("file", help="path to a .csv or .json data file")
    parser.add_argument(
        "--steps",
        nargs="*",
        default=DEFAULT_STEPS,
        metavar="STEP",
        help=f"transformation steps to apply (default: {' '.join(DEFAULT_STEPS)})",
    )
    parser.add_argument(
        "--rules",
        nargs="*",
        default=DEFAULT_RULES,
        metavar="RULE",
        help=f"validation rules to run (default: {' '.join(DEFAULT_RULES)})",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="output format (default: text)",
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        default=None,
        help="write report to FILE instead of stdout",
    )
    args = parser.parse_args()

    try:
        records = load(args.file)
        records = apply(records, args.steps)
        report = validate(records, args.rules)
        write(report, fmt=args.format, dest=args.output)
        sys.exit(0 if report.ok else 1)
    except (ValueError, FileNotFoundError) as err:
        print(f"error: {err}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
