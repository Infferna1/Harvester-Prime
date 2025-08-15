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
from datetime import datetime
import re

import yaml

# Ensure the src directory is on the Python path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR / "src"))

from app.collectors.files import load_dhcp_logs, write_dhcp_interim, list_csv_files
from app.processors.normalize import normalize_dhcp_records


def _format_timestamp(value: str) -> str:
    """Return *value* converted to ``DD.MM.YYYY HH:MM`` format.

    ``value`` is expected to be a Unix timestamp in seconds or milliseconds.
    If it cannot be parsed, an empty string is returned.
    """

    try:
        ts = int(value)
    except ValueError:
        return ""
    if ts > 1_000_000_000_000:  # milliseconds
        ts /= 1000
    return datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")


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

    # Load validation records (ip, mac) normalising MAC to uppercase
    validation_records = []
    if validation_dir.exists():
        for path in validation_dir.glob("*.csv"):
            if path.name.endswith(".example.csv"):
                continue
            with open(path, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    mac = (row.get("mac", "") or "").strip().upper().replace("-", ":")
                    validation_records.append({"ip": row.get("ip", ""), "mac": mac})

    # Load DHCP records indexed by normalised MAC
    dhcp_records = {}
    if dhcp_file.exists():
        with open(dhcp_file, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                mac = (row.get("mac", "") or "").strip().upper().replace("-", ":")
                dhcp_records[mac] = row

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
        first_seen = _format_timestamp(dhcp_row.get("firstDate", ""))
        last_seen = _format_timestamp(dhcp_row.get("lastDate", ""))
        note = "Не надано для перевірки."
        if first_seen or last_seen:
            note += f" Перше підключення – {first_seen}, останнє підключення – {last_seen}."
        report_rows.append(
            {
                "hostname": dhcp_row.get("hostname", ""),
                "ipmac": f"{dhcp_row.get('ip', '')}\n{mac}",
                "note": note,
            }
        )

    file_created = not report_file.exists()
    report_file.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["hostname", "ipmac", "note"]
    with open(report_file, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(report_rows)
    action = "Створено" if file_created else "Оновлено"
    print(f"{action} файл {report_file}")
    print(f"Додано {len(report_rows)} нових записів.")


MAC_RE = re.compile(r"^[0-9A-Fa-f]{2}([-:][0-9A-Fa-f]{2}){5}$")


def run_arm_interim(arm_dir: Path, dhcp_file: Path, checked_file: Path) -> None:
    """Add ARM records matched with DHCP data to *checked_file*.

    Rows are written with columns ``type``, ``name``, ``ip``, ``mac``, ``owner``,
    ``note``, ``firstDate`` and ``lastDate``. Only records where the MAC address
    from ``arm_dir`` is present in ``dhcp_file`` are included. Existing entries
    in *checked_file* are preserved and duplicates are skipped.
    """

    arm_dir = Path(arm_dir)
    dhcp_file = Path(dhcp_file)
    checked_file = Path(checked_file)

    if not dhcp_file.exists():
        print(
            f"Відсутній файл DHCP {dhcp_file}. Крок перевірки ARM (interim) пропущено."
        )
        return

    # Load DHCP records indexed by normalised MAC
    dhcp_records = {}
    with open(dhcp_file, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            mac = (row.get("mac", "") or "").strip().upper().replace("-", ":")
            dhcp_records[mac] = row

    # Load existing MACs from the checked file
    file_created = not checked_file.exists()
    existing_macs = set()
    if not file_created:
        with open(checked_file, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                mac = (row.get("mac", "") or "").strip().upper().replace("-", ":")
                if mac:
                    existing_macs.add(mac)

    rows_to_write = []

    if arm_dir.exists():
        for path in list_csv_files(arm_dir):
            with open(path, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    mac_raw = (row.get("MAC", "") or "").strip()
                    if not MAC_RE.fullmatch(mac_raw):
                        continue
                    mac = mac_raw.upper().replace("-", ":")
                    if mac in existing_macs:
                        continue
                    dhcp_row = dhcp_records.get(mac)
                    if not dhcp_row:
                        continue
                    rows_to_write.append(
                        {
                            "type": "arm",
                            "name": row.get("Hostname", ""),
                            "ip": dhcp_row.get("ip", ""),
                            "mac": mac,
                            "owner": row.get("Власник", ""),
                            "note": row.get("Тип ПК", ""),
                            "firstDate": dhcp_row.get("firstDate", ""),
                            "lastDate": dhcp_row.get("lastDate", ""),
                        }
                    )
                    existing_macs.add(mac)
    else:
        print(f"Відсутні файли для перевірки у {arm_dir}. Крок ARM interim пропущено.")

    if not rows_to_write:
        print(f"Нових записів не додано до {checked_file}.")
        return

    checked_file.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "type",
        "name",
        "ip",
        "mac",
        "owner",
        "note",
        "firstDate",
        "lastDate",
    ]
    mode = "a" if checked_file.exists() else "w"
    with open(checked_file, mode, newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        if mode == "w":
            writer.writeheader()
        writer.writerows(rows_to_write)
    action = "Створено" if file_created else "Оновлено"
    print(f"{action} файл {checked_file}")
    print(f"Додано {len(rows_to_write)} нових записів.")


def run_mkp_interim(mkp_dir: Path, dhcp_file: Path, checked_file: Path) -> None:
    """Add MKP records matched with DHCP data to *checked_file*.

    The behaviour mirrors :func:`run_arm_interim` but works with MKP inventory
    files and writes rows with ``type`` set to ``"mkp"``.
    """

    mkp_dir = Path(mkp_dir)
    dhcp_file = Path(dhcp_file)
    checked_file = Path(checked_file)

    if not dhcp_file.exists():
        print(
            f"Відсутній файл DHCP {dhcp_file}. Крок перевірки МКП (interim) пропущено."
        )
        return

    # Load DHCP records indexed by normalised MAC
    dhcp_records = {}
    with open(dhcp_file, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            mac = (row.get("mac", "") or "").strip().upper().replace("-", ":")
            dhcp_records[mac] = row

    # Load existing MACs from the checked file
    file_created = not checked_file.exists()
    existing_macs = set()
    if not file_created:
        with open(checked_file, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                mac = (row.get("mac", "") or "").strip().upper().replace("-", ":")
                if mac:
                    existing_macs.add(mac)

    rows_to_write = []

    if mkp_dir.exists():
        for path in list_csv_files(mkp_dir):
            with open(path, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    mac_raw = (row.get("Статичний MAC", "") or "").strip()
                    if not MAC_RE.fullmatch(mac_raw):
                        continue
                    mac = mac_raw.upper().replace("-", ":")
                    if mac in existing_macs:
                        continue
                    dhcp_row = dhcp_records.get(mac)
                    if not dhcp_row:
                        continue
                    rows_to_write.append(
                        {
                            "type": "mkp",
                            "name": row.get("Модель", ""),
                            "ip": dhcp_row.get("ip", ""),
                            "mac": mac,
                            "owner": row.get("Відповідальний", ""),
                            "note": row.get("Тип МКП", ""),
                            "firstDate": dhcp_row.get("firstDate", ""),
                            "lastDate": dhcp_row.get("lastDate", ""),
                        }
                    )
                    existing_macs.add(mac)
    else:
        print(f"Відсутні файли для перевірки у {mkp_dir}. Крок МКП interim пропущено.")

    if not rows_to_write:
        print(f"Нових записів не додано до {checked_file}.")
        return

    checked_file.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "type",
        "name",
        "ip",
        "mac",
        "owner",
        "note",
        "firstDate",
        "lastDate",
    ]
    mode = "a" if checked_file.exists() else "w"
    with open(checked_file, mode, newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        if mode == "w":
            writer.writeheader()
        writer.writerows(rows_to_write)
    action = "Створено" if file_created else "Оновлено"
    print(f"{action} файл {checked_file}")
    print(f"Додано {len(rows_to_write)} нових записів.")

def run_arm_check(arm_dir: Path, dhcp_file: Path, report_file: Path) -> None:
    """Generate ARM report from *arm_dir* against *dhcp_file*.

    The report is written to *report_file* with columns ``name``, ``ipmac``,
    ``owner`` and ``note``. Rows are appended only if they are not already
    present in the report.
    """

    arm_dir = Path(arm_dir)
    dhcp_file = Path(dhcp_file)
    report_file = Path(report_file)

    if not dhcp_file.exists():
        print(f"Відсутній файл DHCP {dhcp_file}. Крок перевірки ARM пропущено.")
        return

    # Load DHCP records indexed by normalized MAC
    dhcp_records = {}
    with open(dhcp_file, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            mac = (row.get("mac", "") or "").upper().replace("-", ":")
            dhcp_records[mac] = row

    # Load existing MACs from the report to avoid duplicates
    file_created = not report_file.exists()
    existing_macs = set()
    if not file_created:
        with open(report_file, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                ipmac = row.get("ipmac", "")
                if not ipmac:
                    continue
                parts = ipmac.splitlines()
                if parts:
                    existing_macs.add(parts[-1].strip().upper().replace("-", ":"))

    matched_rows = []
    unmatched_rows = []
    duplicates = 0

    if arm_dir.exists():
        for path in list_csv_files(arm_dir):
            with open(path, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    mac_raw = row.get("MAC", "").strip()
                    if not MAC_RE.fullmatch(mac_raw):
                        continue
                    mac = mac_raw.upper().replace("-", ":")
                    if mac in existing_macs:
                        duplicates += 1
                        continue
                    hostname = row.get("Hostname", "")
                    owner = row.get("Власник", "")
                    type_pc = row.get("Тип ПК", "")
                    dhcp_row = dhcp_records.get(mac)
                    if dhcp_row:
                        matched_rows.append(
                            {
                                "name": f"АРМ\n{hostname}",
                                "ipmac": f"{dhcp_row.get('ip', '')}\n{mac}",
                                "owner": owner,
                                "note": type_pc,
                            }
                        )
                    else:
                        ip = (row.get("IP", "") or "").strip()
                        ipmac = f"{ip}\n{mac}" if ip else f"-\n{mac}"
                        unmatched_rows.append(
                            {
                                "name": f"АРМ\n{hostname}",
                                "ipmac": ipmac,
                                "owner": owner,
                                "note": type_pc,
                            }
                        )
                    existing_macs.add(mac)
    else:
        print(f"Відсутні файли для перевірки у {arm_dir}. Крок ARM пропущено.")

    report_rows = matched_rows + unmatched_rows

    if not report_rows:
        print(
            f"Нових записів не додано до {report_file}. "
            f"{duplicates} записів вже існували."
        )
        return

    report_file.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["name", "ipmac", "owner", "note"]
    mode = "a" if report_file.exists() else "w"
    with open(report_file, mode, newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        if mode == "w":
            writer.writeheader()
        writer.writerows(report_rows)
    action = "Створено" if file_created else "Оновлено"
    print(f"{action} файл {report_file}")
    print(
        f"Додано {len(report_rows)} нових записів. "
        f"{duplicates} записів вже існували та не були додані."
    )


def run_mkp_check(mkp_dir: Path, dhcp_file: Path, report_file: Path) -> None:
    """Generate MKP report from *mkp_dir* against *dhcp_file*.

    Rows are appended to *report_file* with columns ``name``, ``ipmac``,
    ``owner`` and ``note``. Existing entries are not duplicated.
    """

    mkp_dir = Path(mkp_dir)
    dhcp_file = Path(dhcp_file)
    report_file = Path(report_file)

    if not dhcp_file.exists():
        print(f"Відсутній файл DHCP {dhcp_file}. Крок перевірки МКП пропущено.")
        return

    # Load DHCP records indexed by normalised MAC
    dhcp_records = {}
    with open(dhcp_file, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            mac = (row.get("mac", "") or "").strip().upper().replace("-", ":")
            dhcp_records[mac] = row

    # Load existing MACs from the report to avoid duplicates
    file_created = not report_file.exists()
    existing_macs = set()
    if not file_created:
        with open(report_file, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                ipmac = row.get("ipmac", "")
                if not ipmac:
                    continue
                parts = ipmac.splitlines()
                if parts:
                    existing_macs.add(parts[-1].strip().upper().replace("-", ":"))

    matched_rows = []
    unmatched_rows = []
    duplicates = 0

    if mkp_dir.exists():
        for path in list_csv_files(mkp_dir):
            with open(path, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    mac_raw = (row.get("Статичний MAC", "") or "").strip()
                    if not MAC_RE.fullmatch(mac_raw):
                        continue
                    mac = mac_raw.upper().replace("-", ":")
                    if mac in existing_macs:
                        duplicates += 1
                        continue
                    model = row.get("Модель", "")
                    owner = row.get("Відповідальний", "")
                    mkp_type = row.get("Тип МКП", "")
                    dhcp_row = dhcp_records.get(mac)
                    if dhcp_row:
                        matched_rows.append(
                            {
                                "name": f"МКП\n{model}",
                                "ipmac": f"{dhcp_row.get('ip', '')}\n{mac}",
                                "owner": owner,
                                "note": mkp_type,
                            }
                        )
                    else:
                        unmatched_rows.append(
                            {
                                "name": f"МКП\n{model}",
                                "ipmac": mac,
                                "owner": owner,
                                "note": mkp_type,
                            }
                        )
                    existing_macs.add(mac)
    else:
        print(f"Відсутні файли для перевірки у {mkp_dir}. Крок МКП пропущено.")

    report_rows = matched_rows + unmatched_rows

    if not report_rows:
        print(
            f"Нових записів не додано до {report_file}. "
            f"{duplicates} записів вже існували."
        )
        return

    report_file.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["name", "ipmac", "owner", "note"]
    mode = "a" if report_file.exists() else "w"
    with open(report_file, mode, newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        if mode == "w":
            writer.writeheader()
        writer.writerows(report_rows)
    action = "Створено" if file_created else "Оновлено"
    print(f"{action} файл {report_file}")
    print(
        f"Додано {len(report_rows)} нових записів. "
        f"{duplicates} записів вже існували та не були додані."
    )


def main() -> None:
    config = load_config()
    paths = config.get("paths", {})

    raw_dir = BASE_DIR / paths.get("raw_dhcp", "data/raw/dhcp")
    interim_file = BASE_DIR / paths.get("interim_dhcp", "data/interim/dhcp.csv")

    if not list_csv_files(raw_dir):
        print(f"Відсутні файли DHCP у {raw_dir}. Обробку даних не запущено.")
        return

    records = load_dhcp_logs(raw_dir)
    normalized = normalize_dhcp_records(records)
    write_dhcp_interim(interim_file, normalized)

    validation_dir = BASE_DIR / paths.get("raw_validation", "data/raw/validation")
    if list_csv_files(validation_dir):
        report_file = BASE_DIR / paths.get(
            "validation_report", "data/result/report1.csv"
        )
        run_validation(validation_dir, interim_file, report_file)
    else:
        print(
            f"Відсутні файли для валідації у {validation_dir}. Крок перевірки пропущено."
        )

    arm_dir = BASE_DIR / paths.get("raw_arm", "data/raw/arm")
    mkp_dir = BASE_DIR / paths.get("raw_mkp", "data/raw/mkp")
    checked_file = BASE_DIR / "data/interim/checked.csv"
    run_arm_interim(arm_dir, interim_file, checked_file)
    run_mkp_interim(mkp_dir, interim_file, checked_file)
    report_file2 = BASE_DIR / paths.get(
        "arm_mkp_report", "data/result/120report2.csv"
    )
    run_arm_check(arm_dir, interim_file, report_file2)
    run_mkp_check(mkp_dir, interim_file, report_file2)


if __name__ == "__main__":
    main()
