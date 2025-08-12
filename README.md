# Harvester Prime

Utilities for processing DHCP log files.

## Functionality

* Collect DHCP log entries from CSV files in a directory.
* Normalize records into a consistent structure.
* Write results to an interim CSV file while skipping duplicate rows.

## Input

Raw DHCP log CSV files. Locations are configurable via `configs/base.yaml` (default: `data/raw/dhcp`).

## Output

A normalized CSV file containing unique DHCP records (default: `data/interim/dhcp.csv`).

## Usage

Ensure dependencies are installed and run:

```bash
python scripts/process.py
```

The script reads configuration, processes the raw logs and stores the normalized output.

See `src/app/collectors/files.py` for implementation details.
