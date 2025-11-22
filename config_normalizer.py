import csv
import json
import os
import sys
import tkinter as tk


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

# Bruh, this thing is so stupid, I hate tkinter
def add_copy_paste_bindings(widget):
    def handler(event):
        ctrl = (event.state & 0x4) != 0
        if ctrl:
            char = event.char.lower()
            # Діагностичний вивід
            print(f"Pressed char: {repr(char)}, state: {event.state}")

            if char == '\x01':  # Ctrl+A
                widget.event_generate('<<SelectAll>>')
                return "break"
            elif char == '\x03':  # Ctrl+C
                widget.event_generate('<<Copy>>')
                return "break"
            elif char == '\x16':  # Ctrl+V
                widget.event_generate('<<Paste>>')
                return "break"
            elif char == '\x18':  # Ctrl+X
                widget.event_generate('<<Cut>>')
                return "break"
        return None

    widget.bind("<KeyPress>", handler)


def format_mac_address(obj, var, entry, formatting_flag_name: str):
    if getattr(obj, formatting_flag_name, False):
        return

    setattr(obj, formatting_flag_name, True)

    def _format():
        text = var.get()
        cursor_pos = entry.index("insert")
        raw = ''.join(filter(str.isalnum, text.upper()))[:12]
        new_text = ':'.join(raw[i:i+2] for i in range(0, len(raw), 2))

        clean_left = ''.join(filter(str.isalnum, text[:cursor_pos].upper()))
        insert_pos = len(clean_left)
        colons_before = insert_pos // 2
        new_cursor_pos = insert_pos + colons_before

        if var.get() != new_text:
            var.set(new_text)

        try:
            entry.icursor(new_cursor_pos)
        except:
            pass

        setattr(obj, formatting_flag_name, False)

    obj.after_idle(_format)
