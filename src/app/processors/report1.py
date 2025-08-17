"""Generate validation report from verified and pending device lists."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple
import csv
from datetime import datetime


def _format_date(value: str) -> str:
    """Return *value* formatted as ``dd.MM.yyyy HH:mm`` or an empty string."""
    if not value:
        return ""
    try:
        ts = int(value)
        if ts > 1_000_000_000_000:
            ts /= 1000
        return datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%d.%m.%Y %H:%M", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(value, fmt).strftime("%d.%m.%Y %H:%M")
        except ValueError:
            continue
    return ""


def _read_csv(path: Path, columns: List[str]) -> List[Dict[str, str]]:
    """Read *columns* from CSV *path* returning list of rows."""
    rows: List[Dict[str, str]] = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append({col: row.get(col, "") for col in columns})
    return rows


def _load_config(path: Path) -> Tuple[Dict[str, str], str]:
    """Return device mapping and report path from YAML-like *path*."""
    devices: Dict[str, str] = {}
    report_path = "data/result/report1.csv"
    section: str | None = None
    with open(path, encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.rstrip()
            if not line or line.lstrip().startswith("#"):
                continue
            if not line.startswith(" "):
                section = line.rstrip(":")
                continue
            if section == "devices":
                key, _, value = line.strip().partition(":")
                devices[key.strip()] = value.strip().strip('"')
            elif section == "paths":
                key, _, value = line.strip().partition(":")
                if key.strip() == "validation_report":
                    report_path = value.strip()
    if "unknown" not in devices:
        devices["unknown"] = "Невідомий пристрій"
    return devices, report_path


def generate_report(base_dir: Path) -> None:
    """Generate ``report1.csv`` using configuration in *base_dir*."""
    config_path = base_dir / "configs" / "base.yaml"
    devices, report_rel = _load_config(config_path)
    report_path = base_dir / report_rel

    device_order = list(devices.keys())

    verified_path = base_dir / "data/interim/verified.csv"
    pending_path = base_dir / "data/interim/pending.csv"

    verified = _read_csv(verified_path, ["source", "name", "ip", "mac", "type", "note"])
    pending = _read_csv(
        pending_path,
        ["source", "name", "ip", "mac", "type", "firstDate", "lastDate"],
    )

    for row in verified:
        if row.get("type") not in devices:
            row["type"] = "unknown"
    for row in pending:
        if row.get("type") not in devices:
            row["type"] = "unknown"

    sources = sorted({r.get("source", "") for r in verified + pending})

    rows: List[Dict[str, str]] = []
    for source in sources:
        rows.append({"name": "", "ipmac": "", "note": source})
        for dtype in device_order:
            human = devices.get(dtype, devices["unknown"])

            for r in [v for v in verified if v.get("source") == source and v.get("type") == dtype]:
                name_parts = [human, r.get("name", "")]
                note = r.get("note", "")
                if note:
                    name_parts.append(note)
                name_field = "\n".join(name_parts)
                ipmac_field = f"{r.get('ip', '')}\n{r.get('mac', '')}"
                rows.append(
                    {
                        "name": name_field,
                        "ipmac": ipmac_field,
                        "note": "Надано на перевірку.",
                    }
                )

            for r in [p for p in pending if p.get("source") == source and p.get("type") == dtype]:
                name_field = f"{human}\n{r.get('name', '')}"
                ipmac_field = f"{r.get('ip', '')}\n{r.get('mac', '')}"
                first = _format_date(r.get("firstDate", ""))
                last = _format_date(r.get("lastDate", ""))
                note_field = (
                    "Не надано для перевірки. Перше підключення – "
                    f"{first}, останнє підключення – {last}."
                )
                rows.append({"name": name_field, "ipmac": ipmac_field, "note": note_field})

    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["name", "ipmac", "note"])
        writer.writeheader()
        writer.writerows(rows)
