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
    """Load a CSV file and return a list of row dicts."""
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
    """Load a JSON file containing an array of records."""
    with open(path) as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON array, got {type(data).__name__}")
    return data


def load(path: str) -> list[dict]:
    """Dispatch to load_csv or load_json based on file extension."""
    p = Path(path)
    if p.suffix == ".csv":
        return load_csv(path)
    if p.suffix == ".json":
        return load_json(path)
    raise ValueError(f"Unsupported file type: {p.suffix}")
