from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import yaml


class DeviceTypeClassifier:
    """Classify device types based on hostname rules.

    Parameters
    ----------
    rules_path:
        Path to YAML file containing classification rules.
    """

    def __init__(self, rules_path: Path):
        self.rules_path = Path(rules_path)
        with open(self.rules_path, encoding="utf-8") as fh:
            config: dict[str, Any] = yaml.safe_load(fh) or {}

        self.default: str = config.get("default", "unknown")
        options: dict[str, Any] = config.get("options", {})
        self.case_insensitive: bool = bool(options.get("case_insensitive"))
        self.trim: bool = bool(options.get("trim"))

        self.rules: list[dict[str, Any]] = []
        for rule in config.get("rules", []):
            mode = rule.get("mode", "")
            patterns = rule.get("patterns", []) or []
            if mode == "regex":
                flags = re.IGNORECASE if self.case_insensitive else 0
                compiled = [re.compile(pat, flags) for pat in patterns]
            else:
                if self.case_insensitive:
                    patterns = [pat.lower() for pat in patterns]
                compiled = patterns
            self.rules.append({"type": rule.get("type", self.default), "mode": mode, "patterns": compiled})

    def classify(self, hostname: str | None) -> str:
        """Return the device type for *hostname* based on loaded rules."""

        if hostname is None:
            hostname = ""
        if self.trim:
            hostname = hostname.strip()
        cmp_hostname = hostname.lower() if self.case_insensitive else hostname

        for rule in self.rules:
            mode = rule["mode"]
            patterns = rule["patterns"]
            if mode == "regex":
                for pattern in patterns:
                    if pattern.search(hostname):
                        return rule["type"]
            elif mode == "prefix":
                for pat in patterns:
                    if cmp_hostname.startswith(pat):
                        return rule["type"]
            elif mode == "contains":
                for pat in patterns:
                    if pat in cmp_hostname:
                        return rule["type"]
        return self.default
