"""Utilities for working with CSV files."""
from __future__ import annotations

from pathlib import Path
import csv
from typing import Iterable, Dict, List

# Columns we are interested in within DHCP log files
DHCP_COLUMNS = [
    "logSourceIdentifier",
    "sourcMACAddress",
    "payloadAsUTF",
    "deviceTime",
]


def _is_valid_csv(path: Path) -> bool:
    """Return True if *path* points to a CSV file we should process."""
    return path.suffix == ".csv" and not path.name.endswith(".examples.csv")


def list_csv_files(directory: Path) -> List[Path]:
    """List all CSV files within *directory* that should be processed."""
    directory = Path(directory)
    return [p for p in directory.glob("*.csv") if _is_valid_csv(p)]


def read_csv(path: Path, columns: Iterable[str] = DHCP_COLUMNS) -> List[Dict[str, str]]:
    """Read selected *columns* from a CSV file.

    Parameters
    ----------
    path:
        Path to the CSV file.
    columns:
        Iterable with the names of the columns to return.
    """
    rows: List[Dict[str, str]] = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append({col: row.get(col, "") for col in columns})
    return rows


def load_dhcp_logs(directory: Path) -> List[Dict[str, str]]:
    """Load and combine DHCP log entries from all CSV files in *directory*."""
    logs: List[Dict[str, str]] = []
    for file_path in list_csv_files(directory):
        logs.extend(read_csv(file_path))
    return logs


def write_dhcp_interim(path: Path, rows: Iterable[Dict[str, str]]) -> None:
    """Write normalized DHCP rows to *path* in CSV format."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["source", "ip", "mac", "hostname", "date"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
