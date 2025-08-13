"""Script to process raw DHCP log files into a normalized CSV.

This script reads configuration from ``configs/base.yaml`` to determine the
locations of the raw DHCP logs and the destination for the normalized interim
CSV file. The configuration allows these paths to be easily customised without
modifying the code.
"""
from __future__ import annotations

from pathlib import Path
import sys
import csv

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


def run_validation(validation_dir: Path, dhcp_file: Path, report_file: Path) -> None:
    """Validate MAC addresses from *validation_dir* against *dhcp_file*.

    The resulting report is written to *report_file* with columns
    ``hostname``, ``ipmac`` and ``note``.
    """
    validation_dir = Path(validation_dir)
    dhcp_file = Path(dhcp_file)
    report_file = Path(report_file)

    # Load validation records (ip, mac)
    validation_records = []
    if validation_dir.exists():
        for path in validation_dir.glob("*.csv"):
            if path.name.endswith(".example.csv"):
                continue
            with open(path, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    validation_records.append({"ip": row.get("ip", ""), "mac": row.get("mac", "")})

    # Load DHCP records indexed by MAC
    dhcp_records = {}
    if dhcp_file.exists():
        with open(dhcp_file, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                dhcp_records[row.get("mac", "")] = row

    matched_macs = set()
    report_rows = []

    for record in validation_records:
        mac = record.get("mac", "")
        ip = record.get("ip", "")
        dhcp_row = dhcp_records.get(mac)
        if dhcp_row:
            report_rows.append(
                {
                    "hostname": dhcp_row.get("hostname", ""),
                    "ipmac": f"{dhcp_row.get('ip', '')}\n{mac}",
                    "note": "Надано на перевірку.",
                }
            )
            matched_macs.add(mac)
        else:
            report_rows.append(
                {
                    "hostname": "unknown",
                    "ipmac": f"{ip}\n{mac}",
                    "note": "Пристрій відсутній на локації.",
                }
            )

    for mac, dhcp_row in dhcp_records.items():
        if mac in matched_macs:
            continue
        report_rows.append(
            {
                "hostname": dhcp_row.get("hostname", ""),
                "ipmac": f"{dhcp_row.get('ip', '')}\n{mac}",
                "note": "Не надано на перевірку.",
            }
        )

    report_file.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["hostname", "ipmac", "note"]
    with open(report_file, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(report_rows)


def main() -> None:
    config = load_config()
    paths = config.get("paths", {})

    raw_dir = BASE_DIR / paths.get("raw_dhcp", "data/raw/dhcp")
    interim_file = BASE_DIR / paths.get("interim_dhcp", "data/interim/dhcp.csv")

    records = load_dhcp_logs(raw_dir)
    normalized = normalize_dhcp_records(records)
    write_dhcp_interim(interim_file, normalized)

    validation_dir = BASE_DIR / "data" / "raw" / "validation"
    report_file = BASE_DIR / "data" / "result" / "report1.csv"
    run_validation(validation_dir, interim_file, report_file)


if __name__ == "__main__":
    main()
