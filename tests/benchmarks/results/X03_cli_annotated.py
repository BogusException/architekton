"""
Command-line entry point for the data processing pipeline. Accepts a
data file path, an optional list of transformation steps, and an output
format. Ties together data_loader, transformer, validator, and reporter.
"""

import argparse
import sys
from typing import NoReturn

from data_loader import load
from transformer import apply
from validator import validate
from reporter import write


DEFAULT_STEPS: list[str] = ["strip_whitespace", "normalize_value", "add_flag"]
DEFAULT_RULES: list[str] = ["has_id", "value_non_negative", "name_not_empty"]


def main() -> NoReturn:
    """Run the load, transform, validate, report pipeline from the command line.

    Parses sys.argv for a data file path plus the options --steps, --rules,
    --format, and --output. Loads the file, applies the transformation
    steps, validates the records against the rules, and writes the report
    to stdout or to the file given by --output. The function never returns
    normally: it always ends the process through sys.exit.

    Args:
        None. All input comes from sys.argv.

    Returns:
        Never returns. The process exit code is 0 when every record passes
        validation, 1 when at least one record fails, and 2 when loading,
        transforming, or validating raises ValueError or FileNotFoundError.

    Raises:
        SystemExit: Always. Raised by sys.exit with the codes above, or by
            argparse (code 2) when the command-line arguments are invalid
            or when --help is requested (code 0).
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
