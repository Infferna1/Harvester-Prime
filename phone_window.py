import csv
import os
import tkinter as tk
from tkinter import ttk, messagebox
from config_normalizer import load_types_from_json


class PhoneWindow(tk.Toplevel):
    def __init__(self, parent, responsible_value="", department_value=""):
        super().__init__(parent)
        self.title("Введення даних щодо МКП")
        self.parent = parent
        self.mkp_category_var = tk.StringVar(value="особистий")  # дефолтне значення
        self.field_names = load_types_from_json("Data/ConfigData/phone_field_names.json");

        # Завантаження типів із JSON
        self.types_config = load_types_from_json("Data/ConfigData/phone_types.json")

        self.special_types = self.types_config.get("special_types", [])
        self.default_type = self.types_config.get("default", "звичайний")

        self.type_var = tk.StringVar(value=self.default_type)

        self.create_widgets()

        self.responsible_entry.insert(0, responsible_value)
        self.department_entry.insert(0, department_value)
        self.on_type_change()

    def create_widgets(self):
        # Рядок 0
        ttk.Label(self, text="Відповідальний:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.responsible_entry = ttk.Entry(self, width=30)
        self.responsible_entry.grid(row=0, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(self, text="Відділ:").grid(row=0, column=2, sticky="w", padx=5, pady=5)
        self.department_entry = ttk.Entry(self, width=30)
        self.department_entry.grid(row=0, column=3, sticky="w", padx=5, pady=5)

        # Рядок 1
        ttk.Label(self, text="Статичний MAC:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.mac_entry = ttk.Entry(self, width=30)
        self.mac_entry.grid(row=1, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(self, text="Модель:").grid(row=1, column=2, sticky="w", padx=5, pady=5)
        self.model_entry = ttk.Entry(self, width=30)
        self.model_entry.grid(row=1, column=3, sticky="w", padx=5, pady=5)

        # Рядок 2
        ttk.Label(self, text="Динамічний MAC:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.dynamic_mac_entry = ttk.Entry(self, width=30)
        self.dynamic_mac_entry.grid(row=2, column=1, sticky="w", padx=5, pady=5)

        # Рядок 3: Категорія МКП
        ttk.Label(self, text="Категорія МКП:").grid(row=3, column=0, sticky="w", padx=5, pady=5)
        category_frame = ttk.Frame(self)
        category_frame.grid(row=3, column=1, columnspan=3, sticky="w", padx=5, pady=0)
        ttk.Radiobutton(category_frame, text="особистий", variable=self.mkp_category_var, value="особистий").pack(side="left", padx=5)
        ttk.Radiobutton(category_frame, text="робочий", variable=self.mkp_category_var, value="робочий").pack(side="left", padx=5)

        # Рядок 4: Тип МКП
        ttk.Label(self, text="Тип МКП:").grid(row=4, column=0, sticky="w", padx=5, pady=5)
        type_frame = ttk.Frame(self)
        type_frame.grid(row=5, column=0, columnspan=4, sticky="w", padx=10, pady=0)

        # Додаємо "звичайний"
        ttk.Radiobutton(type_frame, text=self.default_type, variable=self.type_var, value=self.default_type, command=self.on_type_change).pack(side="left", padx=5)

        # Додаємо всі типи з special_types
        for type_name in self.special_types:
            ttk.Radiobutton(type_frame, text=type_name, variable=self.type_var, value=type_name, command=self.on_type_change).pack(side="left", padx=5)

        # Рядок 6: AV + S/N
        self.av_var = tk.StringVar()
        self.sn_var = tk.StringVar()

        self.av_frame = ttk.LabelFrame(self, text="AV")
        self.av_frame.grid(row=6, column=0, columnspan=4, sticky="w", padx=10, pady=5)

        self.av_radio_installed = ttk.Radiobutton(self.av_frame, text="Встановлено", variable=self.av_var,
                                                  value="Встановлено", command=self.on_av_change, state="disabled")
        self.av_radio_installed.grid(row=0, column=0, padx=5, pady=2, sticky="w")

        self.av_radio_not_installed = ttk.Radiobutton(self.av_frame, text="Не встановлено", variable=self.av_var,
                                                      value="Не встановлено", command=self.on_av_change, state="disabled")
        self.av_radio_not_installed.grid(row=0, column=1, padx=5, pady=2, sticky="w")

        ttk.Label(self.av_frame, text="S/N:").grid(row=0, column=2, sticky="e", padx=5)
        self.sn_entry = ttk.Entry(self.av_frame, textvariable=self.sn_var, width=30, state="disabled")
        self.sn_entry.grid(row=0, column=3, padx=5, pady=2, sticky="w")

        # Рядок 7: Пошта
        ttk.Label(self, text="Пошта:").grid(row=7, column=0, sticky="e", padx=5, pady=5)
        self.email_entry = ttk.Entry(self, state="disabled", width=70)
        self.email_entry.grid(row=7, column=1, columnspan=3, sticky="w", padx=5, pady=5)

        # Рядок 8: Кнопки
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=8, column=0, columnspan=4, pady=10)

        save_btn = ttk.Button(btn_frame, text="Зберегти", command=self.save_data_to_csv)
        save_btn.pack(side="left", padx=10)

        cancel_btn = ttk.Button(btn_frame, text="Відміна", command=self.cancel)
        cancel_btn.pack(side="left", padx=10)

        self.protocol("WM_DELETE_WINDOW", self.cancel)

    def on_type_change(self):
        current_type = self.type_var.get()
        if current_type in self.special_types:
            self.av_radio_installed.config(state="normal")
            self.av_radio_not_installed.config(state="normal")
            av_value = self.av_var.get()
            if av_value == "Встановлено":
                self.email_entry.delete(0, tk.END)
                self.email_entry.config(state="disabled")
                self.sn_entry.delete(0, tk.END)
                self.sn_entry.config(state="disabled")
            elif av_value == "Не встановлено":
                self.email_entry.config(state="normal")
                self.sn_entry.config(state="normal")
            else:
                self.email_entry.delete(0, tk.END)
                self.email_entry.config(state="disabled")
                self.sn_entry.delete(0, tk.END)
                self.sn_entry.config(state="disabled")
        else:
            self.av_var.set("")
            self.av_radio_installed.config(state="disabled")
            self.av_radio_not_installed.config(state="disabled")
            self.email_entry.delete(0, tk.END)
            self.email_entry.config(state="disabled")
            self.sn_entry.delete(0, tk.END)
            self.sn_entry.config(state="disabled")

    def on_av_change(self):
        if self.av_var.get() == "Встановлено":
            self.email_entry.delete(0, tk.END)
            self.email_entry.config(state="disabled")
            self.sn_entry.delete(0, tk.END)
            self.sn_entry.config(state="disabled")
        else:
            self.email_entry.config(state="normal")
            self.sn_entry.config(state="normal")

    def collect_data(self):
        f = self.field_names

        return {
            f["responsible"]: self.responsible_entry.get(),
            f["department"]: self.department_entry.get(),
            f["staticMac"]: self.mac_entry.get(),
            f["randomMac"]: self.dynamic_mac_entry.get(),
            f["model"]: self.model_entry.get(),
            f["phoneCategory"]: self.mkp_category_var.get(),
            f["phoneType"]: self.type_var.get(),
            f["av"]: self.av_var.get(),
            f["sn"]: self.sn_entry.get(),
            f["mail"]: self.email_entry.get()
        }

    def save_data_to_csv(self):
        data = self.collect_data()
        filename = "collected_phone_data.csv"
        file_exists = os.path.isfile(filename)
        try:
            with open(filename, "a", encoding="utf-8", newline="") as f:
                fieldnames = list(data.keys())
                writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
                if not file_exists:
                    writer.writeheader()
                writer.writerow(data)
            messagebox.showinfo("Успіх", f"Дані успішно збережено у {filename}")
            self.destroy()
        except Exception as e:
            messagebox.showerror("Помилка", f"Не вдалося зберегти дані:\n{e}")

    def save_data(self):
        data = self.collect_data()
        print("Збережені дані:", data)
        self.destroy()

    def cancel(self):
        self.destroy()
