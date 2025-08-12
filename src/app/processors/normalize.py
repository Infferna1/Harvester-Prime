"""Functions for normalizing DHCP log data."""
from __future__ import annotations

import re
from typing import Dict, Iterable, List

PAYLOAD_RE = re.compile(
    r"assigned\s+(?P<ip>\d+\.\d+\.\d+\.\d+)\s+for\s+(?P<mac>[0-9A-Fa-f:]{17})(?:\s+(?P<hostname>[^\s]+))?"
)


def parse_payload(payload: str) -> Dict[str, str]:
    """Extract IP, MAC and hostname from a payload string."""
    match = PAYLOAD_RE.search(payload or "")
    if not match:
        return {"ip": "", "mac": "", "hostname": "unknown"}
    info = match.groupdict()
    if not info.get("hostname"):
        info["hostname"] = "unknown"
    return info


def deduplicate_by_mac(records: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    """Return only the latest record for each MAC address."""
    latest: Dict[str, Dict[str, str]] = {}
    for record in records:
        mac = record.get("sourcMACAddress", "")
        time_str = record.get("deviceTime", "0")
        try:
            timestamp = int(time_str)
        except ValueError:
            timestamp = 0
        stored = latest.get(mac)
        if stored is None or timestamp > int(stored.get("deviceTime", 0)):
            latest[mac] = record
    return list(latest.values())


def normalize_dhcp_records(records: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    """Normalize raw DHCP log records for downstream processing."""
    normalized: List[Dict[str, str]] = []
    for record in deduplicate_by_mac(records):
        payload = parse_payload(record.get("payloadAsUTF", ""))
        normalized.append(
            {
                "source": record.get("logSourceIdentifier", ""),
                "ip": payload.get("ip", ""),
                "mac": payload.get("mac", record.get("sourcMACAddress", "")),
                "hostname": payload.get("hostname", "unknown"),
                "date": record.get("deviceTime", ""),
            }
        )
    return normalized
