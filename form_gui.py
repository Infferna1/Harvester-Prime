import csv
import tkinter as tk
from tkinter import ttk, messagebox
import os
import datetime
import threading
from enum import Enum
from phone_window import PhoneWindow
from usb_window import USBWindow
from system_info_collector import collect_system_info
from config_normalizer import load_types_from_json

# TODO: Normalize result tables in files PC/Phone


# Завантаження enum типів
pc_types_data = load_types_from_json("Data/ConfigData/pc_types.json")
network_types_data = load_types_from_json("Data/ConfigData/network_types.json")

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
        self.agent_id_var = tk.StringVar()
        self.pc_type_var = tk.StringVar(value=PcType.ТИП_1.value)
        self.network_type_var = tk.StringVar(value=NetworkType.МЕРЕЖА_1.value)

        self.bool_fields_config = load_types_from_json("Data/ConfigData/bool_fields_config.json")
        self.field_names = load_types_from_json("Data/ConfigData/pc_field_names.json")
        self.label_to_id = {field["label"]: field["id"] for field in self.bool_fields_config}
        self.bool_vars = {}


        # Для динамічних полів p_software (замість prohibited_software)
        p_soft_conf = next(
            (item for item in self.bool_fields_config if item.get("id") == "pSoftware"),
            None
        )
        if p_soft_conf:
            self.p_software_label = p_soft_conf["label"]
            self.p_software_id = p_soft_conf["id"]

        self.p_software_vars = []
        self.p_software_frame = None

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

        # Дата перевірки / Hostname
        row1 = ttk.Frame(frame)
        row1.pack(fill=tk.X, pady=5)
        ttk.Label(row1, text="Дата перевірки", width=15).pack(side=tk.LEFT)
        self.date_entry = ttk.Entry(row1, width=30)
        self.date_entry.pack(side=tk.LEFT, padx=(0, 20))
        self.date_entry.insert(0, datetime.date.today().strftime("%d-%m-%Y"))
        ttk.Label(row1, text="Hostname", width=15).pack(side=tk.LEFT)
        self.hostname_entry = ttk.Entry(row1, textvariable=self.hostname_var, width=30, state='readonly')
        self.hostname_entry.pack(side=tk.LEFT)

        # S/N / IP
        row2 = ttk.Frame(frame)
        row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="S/N", width=15).pack(side=tk.LEFT)
        self.sn_entry = ttk.Entry(row2, textvariable=self.sn_var, width=30, state='readonly')
        self.sn_entry.pack(side=tk.LEFT, padx=(0, 20))
        ttk.Label(row2, text="IP", width=15).pack(side=tk.LEFT)
        self.ip_entry = ttk.Entry(row2, textvariable=self.ip_var, width=30, state='readonly')
        self.ip_entry.pack(side=tk.LEFT)

        # Static MAC / Random MAC
        row3 = ttk.Frame(frame)
        row3.pack(fill=tk.X, pady=2)
        ttk.Label(row3, text="Static MAC", width=15).pack(side=tk.LEFT)
        self.mac_entry = ttk.Entry(row3, textvariable=self.mac_var, width=30, state='readonly')
        self.mac_entry.pack(side=tk.LEFT, padx=(0, 20))
        ttk.Label(row3, text="Random MAC", width=15).pack(side=tk.LEFT)
        self.random_mac_var = tk.StringVar(value="")
        self.random_mac_entry = ttk.Entry(row3, textvariable=self.random_mac_var, width=30, state='readonly')
        self.random_mac_entry.pack(side=tk.LEFT)

        # Відділ / Власник
        row4 = ttk.Frame(frame)
        row4.pack(fill=tk.X, pady=2)
        ttk.Label(row4, text="Відділ", width=15).pack(side=tk.LEFT)
        ttk.Entry(row4, textvariable=self.department_var, width=30).pack(side=tk.LEFT, padx=(0, 20))
        ttk.Label(row4, text="Власник", width=15).pack(side=tk.LEFT)
        ttk.Entry(row4, textvariable=self.owner_var, width=30).pack(side=tk.LEFT)

        row5 = ttk.Frame(frame)
        row5.pack(fill=tk.X, pady=2)
        ttk.Label(row5, text="Agent ID", width=15).pack(side=tk.LEFT)
        ttk.Entry(row5, textvariable=self.agent_id_var, width=30).pack(side=tk.LEFT, padx=(0, 20))

        # Кнопка "Додати МКП" під відділом і власником
        add_button_frame = ttk.Frame(frame)
        add_button_frame.pack(fill=tk.X, pady=(10, 20))

        btn_args = {'width': 12}
        ttk.Button(add_button_frame, text="Додати МКП", command=self.add_phone_button, **btn_args).pack(side=tk.LEFT, padx=5)
        ttk.Button(add_button_frame, text="USB", command=self.on_usb_click, **btn_args).pack(side=tk.LEFT, padx=5)

        # Логічні параметри
        ttk.Label(frame, text="\nПараметри (Так / Ні):", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(5, 5))

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
                rb = ttk.Radiobutton(container, text=option, variable=var, value=option,
                                     command=lambda l=label: self.on_logic_option_changed(l))
                rb.grid(row=0, column=i + 1, padx=(10, 5))

            # Якщо це "ПЗ", готуємо frame для додаткових полів, схований поки
            if label == self.p_software_label:
                self.p_software_frame = ttk.Frame(frame, padding=(40, 5))
                self.p_software_frame.pack(anchor="w", fill=tk.X, pady=(0, 15))
                self.p_software_frame.pack_forget()

                # Кнопки додати / видалити ПЗ та контейнер для Entry
                self.entries_container = ttk.Frame(self.p_software_frame)
                self.entries_container.pack(anchor="w", fill=tk.X)

                btns_frame = ttk.Frame(self.p_software_frame)
                btns_frame.pack(anchor="w", pady=5)

                ttk.Button(btns_frame, text="Додати поле ПЗ", command=self.add_p_software_entry).pack(side=tk.LEFT, padx=5)
                ttk.Button(btns_frame, text="Видалити поле ПЗ", command=self.remove_p_software_entry).pack(side=tk.LEFT, padx=5)

        # Кнопка Зберегти дані внизу
        save_btn_frame = ttk.Frame(frame)
        save_btn_frame.pack(fill=tk.X, pady=10)
        ttk.Button(save_btn_frame, text="Зберегти дані", command=self.save_data).pack(side=tk.RIGHT, padx=5)

    def on_logic_option_changed(self, label):
        if label == self.p_software_label:
            val = self.bool_vars[label].get()
            if val == "Знайдено":
                self.p_software_frame.pack(anchor="w", fill=tk.X, pady=(0, 15))
                if not self.p_software_vars:
                    self.add_p_software_entry()
            else:
                self.clear_p_software_entries()
                self.p_software_frame.pack_forget()

    def add_p_software_entry(self):
        entry = ttk.Entry(self.entries_container, width=60)
        entry.pack(anchor="w", pady=2)
        self.p_software_vars.append(entry)

    def remove_p_software_entry(self):
        if self.p_software_vars:
            entry = self.p_software_vars.pop()
            entry.destroy()
            # Якщо більше немає полів - переключаємо радіо на "Не знайдено"
            if not self.p_software_vars:
                self.bool_vars[self.p_software_label].set("Не знайдено")
                self.p_software_frame.pack_forget()

    def clear_p_software_entries(self):
        for entry in self.p_software_vars:
            entry.destroy()
        self.p_software_vars.clear()
        self.bool_vars[self.p_software_label].set("Не знайдено")

    def load_system_info(self):
        info = collect_system_info()
        self.after(0, self.update_system_info_fields, info)

    def update_system_info_fields(self, info):
        self.hostname_var.set(info.get("Hostname", ""))
        self.sn_var.set(info.get("BIOS_Serial", ""))
        self.ip_var.set(info.get("IP", ""))
        self.random_mac_var.set(info.get("MAC", ""))

        self.hostname_entry.config(state='normal')
        self.sn_entry.config(state='normal')
        self.ip_entry.config(state='normal')
        self.mac_entry.config(state='normal')
        self.random_mac_entry.config(state='normal')

    def add_phone_button(self):
        responsible = self.owner_var.get()
        department = self.department_var.get()
        add_win = PhoneWindow(self, responsible_value=responsible, department_value=department)
        add_win.grab_set()

    def on_usb_click(self):
        add_win = USBWindow(self)
        add_win.grab_set()

    def save_data(self):
        f = self.field_names

        data = {
            f["pcType"]: self.pc_type_var.get(),
            f["network"]: self.network_type_var.get(),
            f["checkDate"]: self.date_entry.get(),
            f["hostname"]: self.hostname_var.get(),
            f["sn"]: self.sn_var.get().strip(),
            f["ip"]: self.ip_var.get().strip(),
            f["staticMac"]: self.mac_var.get().strip(),
            f["randomMac"]: self.random_mac_var.get().strip(),
            f["department"]: self.department_var.get(),
            f["owner"]: self.owner_var.get(),
            f["agentId"]: self.agent_id_var.get(),
        }

        for label, var in self.bool_vars.items():
            field_id = self.label_to_id.get(label)
            if field_id:
                data[field_id] = var.get()

        # Збираємо список ПЗ, якщо є
        p_software_list = []
        if self.bool_vars.get(self.p_software_label) and self.bool_vars[self.p_software_label].get() == "Знайдено":
            p_software_list = [e.get().strip() for e in self.p_software_vars if e.get().strip()]

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
                if row["sn"] == data["sn"]:
                    if data["ip"] and data["staticMac"]:
                        if row["ip"] == data["ip"] and row["staticMac"] == data["staticMac"]:
                            messagebox.showwarning("Попередження", "Запис з таким S/N, IP і MAC уже існує.")
                            return
                    else:
                        messagebox.showwarning("Попередження", "Запис з таким S/N уже існує.")
                        return

            with open(filename, "a", encoding="utf-8", newline='') as f:
                fieldnames = list(data.keys())
                writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)

                if not file_exists:
                    writer.writeheader()

                writer.writerow(data)

            # Записуємо список ПЗ лише у другий файл
            if p_software_list:
                p_software_filename = "p_software.csv"
                p_software_file_exists = os.path.isfile(p_software_filename)
                col_name = f"{self.p_software_id}"
                with open(p_software_filename, "a", encoding="utf-8", newline='') as pf:
                    writer = csv.DictWriter(pf, fieldnames=["sn", col_name], quoting=csv.QUOTE_ALL)
                    if not p_software_file_exists:
                        writer.writeheader()
                    writer.writerow({
                        "sn": data["sn"],
                        col_name: "; ".join(p_software_list)
                    })

            messagebox.showinfo("Успіх", "Дані успішно збережено у collected_data.csv" +
                                (", та p_software.csv" if p_software_list else ""))

        except Exception as e:
            messagebox.showerror("Помилка", f"Не вдалося зберегти файл:\n{e}")


if __name__ == "__main__":
    app = App()
    app.mainloop()
