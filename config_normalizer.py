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