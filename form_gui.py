import csv
import sys
import tkinter as tk
from tkinter import ttk, messagebox
import os
import json
import datetime
import threading
from enum import Enum
from phone_window import AdditionalWindow
from system_info_collector import collect_system_info


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def load_types_from_json(path):
    full_path = resource_path(path)
    with open(full_path, encoding="utf-8") as f:
        data = json.load(f)
    return data


# Завантаження enum типів
pc_types_data = load_types_from_json("pc_types.json")
network_types_data = load_types_from_json("network_types.json")

PcType = Enum("PcType", {k: v for k, v in pc_types_data.items()})
NetworkType = Enum("NetworkType", {k: v for k, v in network_types_data.items()})


class App(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Збір інформації про ПК")

        self.hostname_var = tk.StringVar(value="")
        self.sn_var = tk.StringVar(value="")
        self.ip_var = tk.StringVar(value="")
        self.mac_var = tk.StringVar(value="")
        self.department_var = tk.StringVar()
        self.owner_var = tk.StringVar()
        self.pc_type_var = tk.StringVar(value=PcType.ТИП_1.value)
        self.network_type_var = tk.StringVar(value=NetworkType.МЕРЕЖА_1.value)

        self.bool_fields_config = load_types_from_json("bool_fields_config.json")
        self.bool_vars = {}

        self.create_widgets()

        threading.Thread(target=self.load_system_info, daemon=True).start()

    def create_widgets(self):
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        # Тип ПК / Мережа
        row0 = ttk.Frame(frame)
        row0.pack(fill=tk.X, pady=5)
        ttk.Label(row0, text="Тип ПК", width=12).pack(side=tk.LEFT)
        ttk.OptionMenu(row0, self.pc_type_var, self.pc_type_var.get(), *[e.value for e in PcType]).pack(side=tk.LEFT, padx=(0, 15))
        ttk.Label(row0, text="Мережа", width=12).pack(side=tk.LEFT)
        ttk.OptionMenu(row0, self.network_type_var, self.network_type_var.get(), *[e.value for e in NetworkType]).pack(side=tk.LEFT, padx=(0, 15))

        # Дата перевірки
        row1 = ttk.Frame(frame)
        row1.pack(fill=tk.X, pady=5)
        ttk.Label(row1, text="Дата перевірки", width=15).pack(side=tk.LEFT)
        self.date_entry = ttk.Entry(row1, width=30)
        self.date_entry.pack(side=tk.LEFT)
        self.date_entry.insert(0, datetime.date.today().strftime("%d-%m-%Y"))

        # Hostname / S/N
        row2 = ttk.Frame(frame)
        row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="Hostname", width=15).pack(side=tk.LEFT)
        self.hostname_entry = ttk.Entry(row2, textvariable=self.hostname_var, width=30, state='readonly')
        self.hostname_entry.pack(side=tk.LEFT, padx=(0, 20))
        ttk.Label(row2, text="S/N", width=15).pack(side=tk.LEFT)
        self.sn_entry = ttk.Entry(row2, textvariable=self.sn_var, width=30, state='readonly')
        self.sn_entry.pack(side=tk.LEFT)

        # IP / MAC
        row3 = ttk.Frame(frame)
        row3.pack(fill=tk.X, pady=2)
        ttk.Label(row3, text="IP", width=15).pack(side=tk.LEFT)
        self.ip_entry = ttk.Entry(row3, textvariable=self.ip_var, width=30, state='readonly')
        self.ip_entry.pack(side=tk.LEFT, padx=(0, 20))
        ttk.Label(row3, text="MAC", width=15).pack(side=tk.LEFT)
        self.mac_entry = ttk.Entry(row3, textvariable=self.mac_var, width=30, state='readonly')
        self.mac_entry.pack(side=tk.LEFT)

        # Відділ / Власник
        row4 = ttk.Frame(frame)
        row4.pack(fill=tk.X, pady=2)
        ttk.Label(row4, text="Відділ", width=15).pack(side=tk.LEFT)
        ttk.Entry(row4, textvariable=self.department_var, width=30).pack(side=tk.LEFT, padx=(0, 20))
        ttk.Label(row4, text="Власник", width=15).pack(side=tk.LEFT)
        ttk.Entry(row4, textvariable=self.owner_var, width=30).pack(side=tk.LEFT)

        # Логічні параметри
        ttk.Label(frame, text="\nПараметри (Так / Ні):", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(15, 5))

        for field in self.bool_fields_config:
            label = field["label"]
            options = field["options"]
            default = field["default"]

            container = ttk.Frame(frame)
            container.pack(anchor="w", pady=2, fill=tk.X)

            ttk.Label(container, text=label, width=30).grid(row=0, column=0, sticky="w")

            var = tk.StringVar(value=default)
            self.bool_vars[label] = var

            for i, option in enumerate(options):
                ttk.Radiobutton(container, text=option, variable=var, value=option).grid(row=0, column=i + 1, padx=(10, 5))

        # Кнопки
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=20)
        ttk.Button(btn_frame, text="Додати МКП", command=self.test_button).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Зберегти дані", command=self.save_data).pack(side=tk.LEFT, padx=5)

    def load_system_info(self):
        info = collect_system_info()
        self.after(0, self.update_system_info_fields, info)

    def update_system_info_fields(self, info):
        self.hostname_var.set(info.get("Hostname", ""))
        self.sn_var.set(info.get("BIOS_Serial", ""))
        self.ip_var.set(info.get("IP", ""))
        self.mac_var.set(info.get("MAC", ""))

        self.hostname_entry.config(state='normal')
        self.sn_entry.config(state='normal')
        self.ip_entry.config(state='normal')
        self.mac_entry.config(state='normal')

    def test_button(self):
        responsible = self.owner_var.get()
        department = self.department_var.get()
        add_win = AdditionalWindow(self, responsible_value=responsible, department_value=department)
        add_win.grab_set()

    def save_data(self):
        data = {
            "Тип ПК": self.pc_type_var.get(),
            "Мережа": self.network_type_var.get(),
            "Дата перевірки": self.date_entry.get(),
            "Hostname": self.hostname_var.get(),
            "S/N": self.sn_var.get().strip(),
            "IP": self.ip_var.get().strip(),
            "MAC": self.mac_var.get().strip(),
            "Відділ": self.department_var.get(),
            "Власник": self.owner_var.get(),
        }

        for key, var in self.bool_vars.items():
            data[key] = var.get()

        filename = "collected_data.csv"
        file_exists = os.path.isfile(filename)

        try:
            existing_data = []
            if file_exists:
                with open(filename, "r", encoding="utf-8", newline='') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        existing_data.append(row)

            for row in existing_data:
                if row["S/N"] == data["S/N"]:
                    if data["IP"] and data["MAC"]:
                        if row["IP"] == data["IP"] and row["MAC"] == data["MAC"]:
                            messagebox.showwarning("Попередження", "Запис з таким S/N, IP і MAC уже існує.")
                            return
                    else:
                        messagebox.showwarning("Попередження", "Запис з таким S/N уже існує.")
                        return

            with open(filename, "a", encoding="utf-8", newline='') as f:
                fieldnames = list(data.keys())
                writer = csv.DictWriter(f, fieldnames=fieldnames)

                if not file_exists:
                    writer.writeheader()

                writer.writerow(data)

            messagebox.showinfo("Успіх", "Дані успішно збережено у collected_data.csv")

        except Exception as e:
            messagebox.showerror("Помилка", f"Не вдалося зберегти файл:\n{e}")


if __name__ == "__main__":
    app = App()
    app.mainloop()
