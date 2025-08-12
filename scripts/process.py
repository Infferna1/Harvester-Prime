"""Script to process raw DHCP log files into a normalized CSV.

This script reads configuration from ``configs/base.yaml`` to determine the
locations of the raw DHCP logs and the destination for the normalized interim
CSV file. The configuration allows these paths to be easily customised without
modifying the code.
"""
from __future__ import annotations

from pathlib import Path
import sys

import yaml

# Ensure the src directory is on the Python path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR / "src"))

from app.collectors.files import load_dhcp_logs, write_dhcp_interim
from app.processors.normalize import normalize_dhcp_records


def load_config() -> dict:
    """Load configuration values from ``configs/base.yaml``."""
    config_path = BASE_DIR / "configs" / "base.yaml"
    with open(config_path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def main() -> None:
    config = load_config()
    paths = config.get("paths", {})

    raw_dir = BASE_DIR / paths.get("raw_dhcp", "data/raw/dhcp")
    interim_file = BASE_DIR / paths.get("interim_dhcp", "data/interim/dhcp.csv")

    records = load_dhcp_logs(raw_dir)
    normalized = normalize_dhcp_records(records)
    write_dhcp_interim(interim_file, normalized)


if __name__ == "__main__":
    main()
