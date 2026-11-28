"""
Reads CSV and JSON data files from disk and returns them as plain Python
dicts or lists. Validates that required columns exist before returning.
Raises ValueError with a human-readable message when validation fails.
"""

import csv
import json
from pathlib import Path
from typing import Any


REQUIRED_COLUMNS: set[str] = {"id", "name", "value", "timestamp"}


def load_csv(path: str) -> list[dict[str, Any]]:
    """Load a CSV file and return a list of row dicts.

    The header row must contain every name in REQUIRED_COLUMNS. Extra
    columns are kept. Every value is returned as a string (or None for
    short rows), because csv.DictReader does no type conversion.

    Args:
        path: Path to the CSV file.

    Returns:
        One dict per data row, keyed by the header names. The list is
        empty when the file has a valid header and no data rows.

    Raises:
        ValueError: If the header is missing or lacks a required column.
        FileNotFoundError: If the file does not exist.
        OSError: If the file cannot be opened or read.
    """
    rows: list[dict[str, Any]] = []
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        headers = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - headers
        if missing:
            raise ValueError(f"CSV missing required columns: {sorted(missing)}")
        for row in reader:
            rows.append(dict(row))
    return rows


def load_json(path: str) -> list[dict[str, Any]]:
    """Load a JSON file containing an array of records.

    Only the top-level type is checked. The records themselves are not
    validated, and REQUIRED_COLUMNS is not enforced.

    Args:
        path: Path to the JSON file.

    Returns:
        The parsed JSON array, unchanged.

    Raises:
        ValueError: If the top-level JSON value is not an array. This
            also covers json.JSONDecodeError (a ValueError subclass),
            which is raised for empty or malformed files.
        FileNotFoundError: If the file does not exist.
        OSError: If the file cannot be opened or read.
    """
    with open(path) as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON array, got {type(data).__name__}")
    return data


def load(path: str) -> list[dict[str, Any]]:
    """Dispatch to load_csv or load_json based on file extension.

    The extension match is case-sensitive: ".CSV" is not accepted.

    Args:
        path: Path to a ".csv" or ".json" file.

    Returns:
        The list of records returned by load_csv or load_json.

    Raises:
        ValueError: If the extension is unsupported, or if the chosen
            loader rejects the file contents.
        FileNotFoundError: If the file does not exist.
        OSError: If the file cannot be opened or read.
    """
    p = Path(path)
    if p.suffix == ".csv":
        return load_csv(path)
    if p.suffix == ".json":
        return load_json(path)
    raise ValueError(f"Unsupported file type: {p.suffix}")
