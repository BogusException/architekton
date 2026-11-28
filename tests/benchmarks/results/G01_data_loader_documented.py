"""
Reads CSV and JSON data files from disk and returns them as plain Python
dicts or lists. Validates that required columns exist before returning.
Raises ValueError with a human-readable message when validation fails.
"""

import csv
import json
from pathlib import Path


REQUIRED_COLUMNS = {"id", "name", "value", "timestamp"}


def load_csv(path: str) -> list[dict]:
    """Load a CSV file and return a list of row dicts.

    Args:
        path: Path to the CSV file.

    Returns:
        list[dict]: One dict per data row, keyed by the header names.

    Raises:
        ValueError: If a required column is missing from the header, or if the
            file cannot be decoded.
        OSError: If the file cannot be opened or read.
        csv.Error: If the file is malformed CSV.
    """
    rows = []
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        headers = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - headers
        if missing:
            raise ValueError(f"CSV missing required columns: {sorted(missing)}")
        for row in reader:
            rows.append(dict(row))
    return rows


def load_json(path: str) -> list[dict]:
    """Load a JSON file containing an array of records.

    Args:
        path: Path to the JSON file.

    Returns:
        list[dict]: The parsed top-level array. The items are not checked.

    Raises:
        ValueError: If the top-level value is not an array, or if the file is
            not valid JSON (json.JSONDecodeError) or cannot be decoded.
        OSError: If the file cannot be opened or read.
    """
    with open(path) as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON array, got {type(data).__name__}")
    return data


def load(path: str) -> list[dict]:
    """Dispatch to load_csv or load_json based on file extension.

    The extension match is case-sensitive: only ".csv" and ".json" are accepted.

    Args:
        path: Path to a .csv or .json file.

    Returns:
        list[dict]: The records returned by load_csv or load_json.

    Raises:
        ValueError: If the extension is not .csv or .json, or if the selected
            loader raises ValueError.
        OSError: If the selected loader cannot open or read the file.
        csv.Error: If a .csv file is malformed.
    """
    p = Path(path)
    if p.suffix == ".csv":
        return load_csv(path)
    if p.suffix == ".json":
        return load_json(path)
    raise ValueError(f"Unsupported file type: {p.suffix}")
