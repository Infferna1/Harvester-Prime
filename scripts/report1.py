"""Generate report1.csv from verified and pending device lists."""
from __future__ import annotations

from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR / "src"))

from app.processors.report1 import generate_report


if __name__ == "__main__":
    generate_report(BASE_DIR)
