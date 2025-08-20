import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import csv
import json
import re
import sys
from config_normalizer import resource_path


# === Універсальна функція для відкриття текстових файлів ===
def open_text_file(file_path, mode="r"):
    """
    Відкриває файл у UTF-8, якщо не вдалося — у CP1251.
    Працює тільки для читання ("r").
    """
    if "r" not in mode:
        raise ValueError("open_text_file використовується лише для читання!")

    try:
        return open(file_path, mode, encoding="utf-8")
    except UnicodeDecodeError:
        return open(file_path, mode, encoding="cp1251")


# === Завантаження JSON ===
def load_json_file(file_path):
    full_path = resource_path(file_path)
    with open(full_path, encoding="utf-8") as f:
        return json.load(f)


class IgnoreSNWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Ігнорування серійних номерів")
        self.geometry("400x400")

        ttk.Label(self, text="Введіть серійні номери, які потрібно ігнорувати:").pack(padx=10, pady=10)

        self.ignore_sn_entries = []
        self.entry_frame = ttk.Frame(self)
        self.entry_frame.pack(fill="both", expand=True)

        self.add_ignore_sn_field()

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", pady=10)

        ttk.Button(btn_frame, text="Додати", command=self.add_ignore_sn_field).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Видалити", command=self.remove_ignore_sn_field).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Зберегти", command=self.on_confirm).pack(side="left", padx=5)

        self.focus()

    def add_ignore_sn_field(self):
        entry_var = tk.StringVar()
        ignore_sn_entry = ttk.Entry(self.entry_frame, textvariable=entry_var, width=40)
        ignore_sn_entry.pack(fill="x", padx=10, pady=5)
        self.ignore_sn_entries.append(ignore_sn_entry)

    def remove_ignore_sn_field(self):
        if len(self.ignore_sn_entries) > 1:
            last_entry = self.ignore_sn_entries.pop()
            last_entry.destroy()

    def on_confirm(self):
        ignore_sn = [entry.get() for entry in self.ignore_sn_entries if entry.get().strip() != ""]
        if ignore_sn:
            self.master.set_ignore_sn(ignore_sn)
        self.destroy()


class USBFilterWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Фільтрація USB")
        self.geometry("800x700")
        self.ignore_sn = []
        self._build_ui()

    def set_ignore_sn(self, ignore_sn_list):
        self.ignore_sn = ignore_sn_list

    def _get_s_level_from_second_file(self, serial_number, second_file_path, type_map):
        suffix = serial_number[-6:]

        # Беремо мапу рівнів
        s_levels = type_map

        # Формуємо regex із значень
        regex_values = [v for v in s_levels.values() if v != "Неідентифіковано"]
        regex_pattern = r"(" + "|".join(map(re.escape, regex_values)) + r")"

        encodings = ["utf-8", "cp1251"]
        for enc in encodings:
            try:
                print(f"[INFO] Спроба відкриття файлу {second_file_path} з кодуванням {enc}")
                with open(second_file_path, "r", encoding=enc, newline="") as f:
                    reader = csv.reader(f, delimiter=";")
                    for row_count, row in enumerate(reader, start=1):
                        if len(row) < 5:
                            continue
                        sn = row[4].strip()
                        ob_num = row[1].strip()

                        if suffix and suffix in sn:
                            print(f"[MATCH] Суфікс '{suffix}' знайдено в серійному номері '{sn}'")
                            match = re.search(regex_pattern, ob_num, re.IGNORECASE)
                            if match:
                                found_value = match.group(1)
                                # Знаходимо ключ за значенням
                                key = next((k for k, v in s_levels.items() if v.lower() == found_value.lower()),
                                           None)
                                result = s_levels.get(key, s_levels.get("Неідентифіковано"))
                                return result

            except UnicodeDecodeError:
                print(f"[WARNING] Не вдалося відкрити файл з кодуванням {enc}, пробуємо інше")
                continue
            except Exception as e:
                print(f"[ERROR] Помилка при обробці другого файлу: {e}")

        fallback_result = s_levels.get("Неідентифіковано", "Неідентифіковано")
        print(f"[RESULT] За замовчуванням повертаємо: {fallback_result}")
        return fallback_result

    def _build_ui(self):
        labels = load_json_file("Data/ConfigData/labels_w_usb.json")
        usb_columns_config = load_json_file("Data/ConfigData/UsbData/usb_columns_config.json")
        device_types = load_json_file("Data/ConfigData/UsbData/usb_types.json")

        if not labels or not usb_columns_config or not device_types:
            messagebox.showerror("Помилка", "Не вдалося завантажити дані з файлів.")
            self.destroy()
            return

        type_map = usb_columns_config.get("sLevel", {})
        if not type_map:
            messagebox.showerror("Помилка", "У файлі usb_columns_config.json відсутній ключ 'sLevel'.")
            self.destroy()
            return

        types_list = list(type_map.values())

        ignore_sn_window = IgnoreSNWindow(self)
        self.wait_window(ignore_sn_window)

        # Перший CSV
        file_path = filedialog.askopenfilename(
            parent=self,
            title="Оберіть CSV файл з USB пристроями",
            filetypes=[("CSV Files", "*.csv")]
        )
        if not file_path:
            self.destroy()
            return

        serials = self._read_csv(file_path, device_types["device_types"])
        serials = [sn for sn in serials if sn not in self.ignore_sn]

        if not serials:
            messagebox.showinfo(self, "Фільтр", "Не знайдено пристроїв після фільтрації")
            self.destroy()
            return

        # Другий CSV
        second_file_path = filedialog.askopenfilename(
            parent=self,
            title="Оберіть другий CSV (журнал МНІ)",
            filetypes=[("CSV Files", "*.csv")]
        )
        if not second_file_path:
            self.destroy()
            return

        self.entries = []
        max_width = 0

        main_frame = ttk.Frame(self)
        main_frame.pack(fill="both", expand=True, padx=5)

        canvas_frame = ttk.Frame(main_frame)
        canvas_frame.pack(fill="both", expand=True)

        canvas = tk.Canvas(canvas_frame)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner_frame = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=inner_frame, anchor="nw")

        def on_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        inner_frame.bind("<Configure>", on_configure)

        header = ttk.Frame(inner_frame)
        header.grid(row=0, column=0, sticky="w", padx=5, pady=5)

        inner_frame.grid_columnconfigure(0, weight=1)
        inner_frame.grid_columnconfigure(1, weight=3)
        inner_frame.grid_columnconfigure(2, weight=4)

        label_counter = ttk.Label(header, text=labels["number_label"], width=10, anchor="w")
        label_counter.grid(row=0, column=0, sticky="nsew", padx=5)

        label_serial = ttk.Label(header, text=labels["serial_label"], width=32, anchor="w")
        label_serial.grid(row=0, column=1, sticky="nsew", padx=5)

        label_type = ttk.Label(header, text=labels["type_label"], width=15, anchor="w")
        label_type.grid(row=0, column=2, sticky="nsew", padx=5)

        max_width = max(max_width, label_serial.winfo_reqwidth(), label_type.winfo_reqwidth())

        first_entry = None
        counter = 1

        for sn in serials:
            row = ttk.Frame(inner_frame)
            row.grid(row=counter, column=0, sticky="w", pady=2)

            label_counter = ttk.Label(row, text=str(counter), width=10, anchor="center")
            label_counter.grid(row=0, column=0, sticky="ew")

            label_sn = ttk.Label(row, text=sn, width=35, anchor="w")
            label_sn.grid(row=0, column=1, sticky="w")

            auto_type = self._get_s_level_from_second_file(sn, second_file_path, type_map)
            type_var = tk.StringVar(value=auto_type)

            cmb = ttk.Combobox(row, textvariable=type_var, values=types_list, width=20, state="readonly")
            cmb.grid(row=0, column=2, sticky="w", padx=5)

            total_width = label_counter.winfo_reqwidth() + label_sn.winfo_reqwidth() + cmb.winfo_reqwidth()
            max_width = max(max_width, total_width)

            if first_entry is None:
                first_entry = cmb

            self.entries.append((sn, type_var))
            counter += 1

        if first_entry:
            self.after(100, lambda: first_entry.focus_force())

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="Зберегти", command=self._on_save).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Відміна", command=self.destroy).pack(side="left", padx=5)

        self.update_idletasks()
        self.geometry(f"{max_width + 50}x{self.winfo_height()}")
        self.minsize(max_width + 50, self.winfo_height())

        canvas.bind_all("<MouseWheel>", lambda event, canvas=canvas: self._on_mousewheel(event, canvas))

    def _on_mousewheel(self, event, canvas):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _read_csv(self, path, valid_types):
        result = []
        try:
            with open_text_file(path, "r") as f:
                reader = csv.reader(f)
                for rec in reader:
                    if len(rec) >= 3 and rec[1] in valid_types:
                        result.append(rec[2])
        except Exception as e:
            print(f"Помилка при відкритті CSV {path}: {e}")

        return result

    def _on_save(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv")],
            title="Зберегти файл як"
        )

        if not file_path:
            return

        data = [(sn, t.get()) for (sn, t) in self.entries]

        # Запис завжди у utf-8
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, quoting=csv.QUOTE_ALL)
            for rec in data:
                writer.writerow(rec)

        print(f"Збережено в {file_path}")
        self.destroy()
