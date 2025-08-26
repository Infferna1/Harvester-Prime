import csv
import json
import os
import sys


def resource_path(relative_path):
    if getattr(sys, "frozen", False):
        # Якщо exe
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)



def load_types_from_json(path):
    full_path = resource_path(path)
    with open(full_path, encoding="utf-8") as f:
        return json.load(f)


def calculateNextNumber(file_exists, filename):
    next_number = 1
    if file_exists:
        try:
            with open(filename, "r", encoding="utf-8", newline='') as fcsv:
                reader = csv.DictReader(fcsv)
                rows = list(reader)
                if rows:
                    # Беремо останній номер і додаємо +1
                    last_row = rows[-1]
                    try:
                        next_number = int(last_row.get("numberInOrder", len(rows))) + 1
                    except ValueError:
                        next_number = len(rows) + 1
        except Exception as e:
            print(f"[WARN] Не вдалося визначити numberInOrder: {e}")
            next_number = 1
    return next_number