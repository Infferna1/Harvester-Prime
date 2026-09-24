import csv
import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog

from config_normalizer import load_types_from_json, calculateNextNumber, add_copy_paste_bindings, format_mac_address

# Окрема тека конфігів для МКП 2.0, щоб зміни тут не зачіпали стару
# гілку (phone_window.py та її конфіги в Data/ConfigData/).
CONFIG_DIR = "Data/ConfigData/PhoneData"


def _get_app_dir():
    """
    Тека, де фізично лежить .exe (у режимі PyInstaller) або цей .py файл
    (при розробці) - НЕ поточна робоча тека (os.getcwd()). cwd залежить
    від того, звідки застосунок запущено (ярлик з іншим "Start in",
    запуск із консолі з іншої теки тощо) і не завжди збігається з текою
    самого .exe. Дані (CSV) навмисно зберігаємо саме тут, щоб застосунок
    завжди знаходив свій же файл, незалежно від способу запуску.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CSV_FILENAME = os.path.join(_get_app_dir(), "collected_phone_data_v2.csv")

def _load_csv_fields_order():
    return load_types_from_json(f"{CONFIG_DIR}/csv_fields_order.json")["fields"]


def _load_report_header():
    return load_types_from_json(f"{CONFIG_DIR}/report_header.json")["header"]


def format_ip_address(obj, var, entry, formatting_flag_name: str):
    """
    Аналог format_mac_address (config_normalizer.py), але для IPv4.

    Залишає лише цифри та крапки, розбиває на групи максимум по 3 цифри,
    кожна група обрізається так, щоб не перевищувати 255, автоматично
    розставляє крапки. Максимум 4 групи (255.255.255.255).
    """
    if getattr(obj, formatting_flag_name, False):
        return
    setattr(obj, formatting_flag_name, True)
    try:
        raw = var.get()
        try:
            cursor = entry.index(tk.INSERT)
        except Exception:
            cursor = len(raw)

        digits_only = "".join(ch for ch in raw if ch.isdigit())
        digits_only = digits_only[:12]  # 4 групи по максимум 3 цифри

        groups = []
        i = 0
        while i < len(digits_only) and len(groups) < 4:
            group = digits_only[i:i + 3]
            while len(group) > 1 and int(group) > 255:
                group = group[:-1]
            groups.append(group)
            i += len(group)

        formatted = ".".join(groups)

        if formatted != raw:
            var.set(formatted)
            new_cursor = min(len(formatted), cursor + (len(formatted) - len(raw)))
            try:
                entry.icursor(new_cursor)
            except Exception:
                pass
    finally:
        obj.after_idle(lambda: setattr(obj, formatting_flag_name, False))


class PhoneWindowV2(tk.Toplevel):
    """
    МКП 2.0 (хаб) — заміна старого PhoneWindow, незалежна від нього.

    Замість одразу форми відкриває невелике вікно з двома кнопками:
    "Додати МКП" (заповнення однієї картки МКП, дані дописуються в
    collected_phone_data_v2.csv) та "Згенерувати звіт" (формує підсумковий
    .xlsx звіт за прикладом користувача на основі накопиченого CSV).
    """

    def __init__(self, parent, responsible_value="", department_value=""):
        super().__init__(parent)
        self.title("МКП 2.0")
        self.parent = parent
        self.responsible_value = responsible_value
        # department_value наразі не використовується у звіті МКП 2.0,
        # залишено в сигнатурі лише для сумісності виклику з form_gui.py.

        self.resizable(False, False)

        frame = ttk.Frame(self, padding=20)
        frame.pack()

        ttk.Label(frame, text="МКП 2.0", font=("Segoe UI", 12, "bold")).pack(pady=(0, 15))

        ttk.Button(frame, text="Додати МКП", width=25, command=self.open_add_window).pack(pady=5)
        ttk.Button(frame, text="Згенерувати звіт", width=25, command=self.generate_report).pack(pady=5)

    def open_add_window(self):
        add_win = PhoneEntryWindowV2(self, responsible_value=self.responsible_value)
        add_win.grab_set()

    def generate_report(self):
        generate_phone_report_v2(self)


class PhoneEntryWindowV2(tk.Toplevel):
    """Форма введення однієї картки МКП (2.0)."""

    def __init__(self, parent, responsible_value=""):
        super().__init__(parent)
        self.title("Введення даних щодо МКП (2.0)")
        self.parent = parent

        self.field_names = load_types_from_json(f"{CONFIG_DIR}/phone_field_names.json")
        self.presence_labels = load_types_from_json(f"{CONFIG_DIR}/presence_labels.json")
        spz_config = load_types_from_json(f"{CONFIG_DIR}/spz_options.json")
        self.spz_options = spz_config.get("options", ["-"])

        self.phoneCategory_var = tk.StringVar(value="Особистий")
        self.toggle_vars = {}  # field_key -> StringVar

        self.create_widgets()

        self.responsible_entry.insert(0, responsible_value)

    # --- допоміжне створення toggle-полів (Присутнє/Відсутнє тощо) ---
    def _make_toggle(self, parent, row, label_text, field_key, command=None):
        labels = self.presence_labels.get(field_key, {"positive": "Присутнє", "negative": "Відсутнє"})
        var = tk.StringVar(value=labels["negative"])
        self.toggle_vars[field_key] = var

        ttk.Label(parent, text=label_text).grid(row=row, column=0, sticky="w", padx=5, pady=4)
        toggle_frame = ttk.Frame(parent)
        toggle_frame.grid(row=row, column=1, columnspan=3, sticky="w", padx=5, pady=4)
        ttk.Radiobutton(toggle_frame, text=labels["positive"], variable=var,
                         value=labels["positive"], command=command).pack(side="left", padx=5)
        ttk.Radiobutton(toggle_frame, text=labels["negative"], variable=var,
                         value=labels["negative"], command=command).pack(side="left", padx=5)
        return var

    def create_widgets(self):
        row = 0

        # Відповідальна особа
        ttk.Label(self, text="Відповідальна особа:").grid(row=row, column=0, sticky="w", padx=5, pady=5)
        self.responsible_entry = ttk.Entry(self, width=30)
        add_copy_paste_bindings(self.responsible_entry)
        self.responsible_entry.grid(row=row, column=1, sticky="w", padx=5, pady=5)

        # Назва пристрою
        ttk.Label(self, text="Назва пристрою:").grid(row=row, column=2, sticky="w", padx=5, pady=5)
        self.device_name_entry = ttk.Entry(self, width=30)
        add_copy_paste_bindings(self.device_name_entry)
        self.device_name_entry.grid(row=row, column=3, sticky="w", padx=5, pady=5)
        row += 1

        # IP-адреса (з автоформатуванням)
        self.ip_var = tk.StringVar()
        ttk.Label(self, text="IP-адреса:").grid(row=row, column=0, sticky="w", padx=5, pady=5)
        self.ip_entry = ttk.Entry(self, width=30, textvariable=self.ip_var)
        self.ip_var.trace_add("write", lambda *args: format_ip_address(self, self.ip_var, self.ip_entry, "_formatting_ip"))
        add_copy_paste_bindings(self.ip_entry)
        self.ip_entry.grid(row=row, column=1, sticky="w", padx=5, pady=5)

        # MAC-адреса (існуюче автоформатування, залишаємо як є)
        self.mac_var = tk.StringVar()
        ttk.Label(self, text="MAC-адреса:").grid(row=row, column=2, sticky="w", padx=5, pady=5)
        self.mac_entry = ttk.Entry(self, width=30, textvariable=self.mac_var)
        self.mac_var.trace_add("write", lambda *args: format_mac_address(self, self.mac_var, self.mac_entry, "_formatting_mac"))
        add_copy_paste_bindings(self.mac_entry)
        self.mac_entry.grid(row=row, column=3, sticky="w", padx=5, pady=5)
        row += 1

        # Random MAC - зберігається в CSV, але у звіт НЕ виводиться
        # (report_header.json його не містить, у report_row не додається).
        self.random_mac_var = tk.StringVar()
        ttk.Label(self, text="Випадковий MAC:").grid(row=row, column=0, sticky="w", padx=5, pady=5)
        self.random_mac_entry = ttk.Entry(self, width=30, textvariable=self.random_mac_var)
        self.random_mac_var.trace_add(
            "write", lambda *args: format_mac_address(self, self.random_mac_var, self.random_mac_entry, "_formatting_random_mac")
        )
        add_copy_paste_bindings(self.random_mac_entry)
        self.random_mac_entry.grid(row=row, column=1, sticky="w", padx=5, pady=5)
        row += 1

        # Тип МКП: Особистий / Робочий
        ttk.Label(self, text="Тип МКП:").grid(row=row, column=0, sticky="w", padx=5, pady=5)
        type_frame = ttk.Frame(self)
        type_frame.grid(row=row, column=1, columnspan=3, sticky="w", padx=5, pady=5)
        ttk.Radiobutton(type_frame, text="Особистий", variable=self.phoneCategory_var, value="Особистий").pack(side="left", padx=5)
        ttk.Radiobutton(type_frame, text="Робочий", variable=self.phoneCategory_var, value="Робочий").pack(side="left", padx=5)
        row += 1

        # Toggle-поля
        self._make_toggle(self, row, "Заявка на підключення до мережі Інтернет:", "internetRequest"); row += 1
        self._make_toggle(self, row, "Закріплення ІР-адреси за MAC-адресою:", "ipMacBinding"); row += 1

        # СПЗ - випадаючий список
        ttk.Label(self, text="СПЗ:").grid(row=row, column=0, sticky="w", padx=5, pady=5)
        self.spz_var = tk.StringVar(value=self.spz_options[0] if self.spz_options else "-")
        self.spz_combo = ttk.Combobox(self, textvariable=self.spz_var, values=self.spz_options, state="readonly", width=27)
        self.spz_combo.grid(row=row, column=1, sticky="w", padx=5, pady=5)
        row += 1

        self._make_toggle(self, row, "Trellix Mobile Security:", "hx"); row += 1
        self._make_toggle(self, row, "ШПЗ:", "shpz"); row += 1

        # Стороннє ПЗ + список (через кому), активний лише якщо "Присутнє"
        self._make_toggle(self, row, "Стороннє ПЗ:", "thirdPartySoftware", command=self._on_third_party_change)
        row += 1
        ttk.Label(self, text="Яке саме (через кому):").grid(row=row, column=0, sticky="w", padx=5, pady=5)
        self.third_party_list_entry = ttk.Entry(self, width=60, state="disabled")
        self.third_party_list_entry.grid(row=row, column=1, columnspan=3, sticky="w", padx=5, pady=5)
        row += 1

        self._make_toggle(self, row, "Сторонні сесії:", "thirdPartySessions"); row += 1
        self._make_toggle(self, row, "Режим польоту:", "flightMode"); row += 1
        self._make_toggle(self, row, "Увімкнений режим визначення геолокації:", "geolocation"); row += 1
        self._make_toggle(self, row, "Наявність документів з обмеженим доступом:", "restrictedDocs"); row += 1

        # Кнопки
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=row, column=0, columnspan=4, pady=15)
        ttk.Button(btn_frame, text="Зберегти", command=self.save_data_to_csv).pack(side="left", padx=10)
        ttk.Button(btn_frame, text="Відміна", command=self.cancel).pack(side="left", padx=10)

        self.protocol("WM_DELETE_WINDOW", self.cancel)

    def _on_third_party_change(self):
        labels = self.presence_labels.get("thirdPartySoftware", {"positive": "Присутнє"})
        if self.toggle_vars["thirdPartySoftware"].get() == labels["positive"]:
            self.third_party_list_entry.config(state="normal")
            add_copy_paste_bindings(self.third_party_list_entry)
        else:
            self.third_party_list_entry.delete(0, tk.END)
            self.third_party_list_entry.config(state="disabled")

    def collect_data(self):
        f = self.field_names
        return {
            f["phoneCategory"]: self.phoneCategory_var.get(),
            f["deviceName"]: self.device_name_entry.get(),
            f["responsible"]: self.responsible_entry.get(),
            f["ip"]: self.ip_entry.get(),
            f["mac"]: self.mac_entry.get(),
            f["randomMac"]: self.random_mac_entry.get(),
            f["internetRequest"]: self.toggle_vars["internetRequest"].get(),
            f["ipMacBinding"]: self.toggle_vars["ipMacBinding"].get(),
            f["spz"]: self.spz_var.get(),
            f["hx"]: self.toggle_vars["hx"].get(),
            f["shpz"]: self.toggle_vars["shpz"].get(),
            f["thirdPartySoftware"]: self.toggle_vars["thirdPartySoftware"].get(),
            f["thirdPartySoftwareList"]: self.third_party_list_entry.get(),
            f["thirdPartySessions"]: self.toggle_vars["thirdPartySessions"].get(),
            f["flightMode"]: self.toggle_vars["flightMode"].get(),
            f["geolocation"]: self.toggle_vars["geolocation"].get(),
            f["restrictedDocs"]: self.toggle_vars["restrictedDocs"].get(),
        }

    def save_data_to_csv(self):
        if not self.device_name_entry.get().strip():
            messagebox.showwarning("Увага", "Вкажіть назву пристрою.")
            return

        collected = self.collect_data()
        filename = CSV_FILENAME
        file_exists = os.path.isfile(filename)

        next_number = calculateNextNumber(file_exists, filename)

        data = {"numberInOrder": next_number}
        data.update(collected)

        try:
            with open(filename, "a", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=_load_csv_fields_order(), quoting=csv.QUOTE_ALL)
                if not file_exists:
                    writer.writeheader()
                writer.writerow(data)
            messagebox.showinfo("Успіх", f"Дані успішно збережено у {filename}")
            self.destroy()
        except Exception as e:
            messagebox.showerror("Помилка", f"Не вдалося зберегти дані:\n{e}")

    def cancel(self):
        self.destroy()


def _read_collected_csv(csv_path):
    rows = []
    if not csv_path or not os.path.isfile(csv_path):
        return rows
    for encoding in ("utf-8", "cp1251"):
        try:
            with open(csv_path, "r", encoding=encoding, newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            return rows
        except UnicodeDecodeError:
            continue
    return rows


def _to_plus_minus(value, labels):
    """value == labels['positive'] -> '+', інакше '-' (labels: {'positive':..,'negative':..})."""
    positive = labels.get("positive", "")
    return "+" if value == positive else "-"


def generate_phone_report_v2(master):
    try:
        import openpyxl
        from openpyxl.utils import get_column_letter
    except ImportError:
        messagebox.showerror("Помилка", "Бібліотека openpyxl не встановлена.")
        return

    # Файл із сирими даними обираємо вручну щоразу (як і крок "Ідентифікувати
    # ЗНІ" в USB 2.0) - зручно, коли даних декілька (з різних машин/сесій) і
    # не завжди хочеться брати саме collected_phone_data_v2.csv поруч з .exe.
    initial_dir = os.path.dirname(CSV_FILENAME) if os.path.isfile(CSV_FILENAME) else _get_app_dir()
    initial_file = os.path.basename(CSV_FILENAME) if os.path.isfile(CSV_FILENAME) else ""
    csv_path = filedialog.askopenfilename(
        title="Оберіть CSV з даними МКП",
        filetypes=[("CSV Files", "*.csv")],
        initialdir=initial_dir,
        initialfile=initial_file,
        parent=master,
    )
    if not csv_path:
        return

    rows = _read_collected_csv(csv_path)
    if not rows:
        messagebox.showwarning("Увага", f"Файл {csv_path} відсутній або порожній.")
        return

    punkt = simpledialog.askstring("Пункт", "Введіть значення для стовпця «Пункт» (однакове для всього звіту):", parent=master)
    if punkt is None:
        return

    presence_labels = load_types_from_json(f"{CONFIG_DIR}/presence_labels.json")
    order_165_rules = load_types_from_json(f"{CONFIG_DIR}/order_165_rules.json")
    requirements = order_165_rules.get("requirements", [])
    compliant_text = order_165_rules.get("compliantText", "+")
    non_compliant_text = order_165_rules.get("nonCompliantText", "-(надано рекомендації щодо налаштування)")

    def pm(field_key, raw_value):
        labels = presence_labels.get(field_key, {"positive": "Присутнє", "negative": "Відсутнє"})
        return _to_plus_minus(raw_value, labels)

    report_header = _load_report_header()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Звіт"
    ws.append(report_header)

    for idx, row in enumerate(rows, start=1):
        third_party_raw = row.get("thirdPartySoftware", "")
        third_party_mark = pm("thirdPartySoftware", third_party_raw)
        third_party_list = (row.get("thirdPartySoftwareList") or "").strip()
        if third_party_mark == "+" and third_party_list:
            third_party_cell = f"+ ({third_party_list})"
        else:
            third_party_cell = third_party_mark

        # Налаштування (наказ №165) - за конфігурованим набором вимог
        compliant = True
        for req in requirements:
            field = req.get("field")
            required_value = req.get("requiredValue")
            if row.get(field, "") != required_value:
                compliant = False
                break
        order_165_cell = compliant_text if compliant else non_compliant_text

        report_row = [
            idx,
            punkt,
            row.get("phoneCategory", ""),
            row.get("deviceName", ""),
            row.get("responsible", ""),
            row.get("ip", ""),
            row.get("mac", ""),
            pm("internetRequest", row.get("internetRequest", "")),
            pm("ipMacBinding", row.get("ipMacBinding", "")),
            row.get("spz", ""),
            pm("hx", row.get("hx", "")),
            pm("shpz", row.get("shpz", "")),
            third_party_cell,
            pm("thirdPartySessions", row.get("thirdPartySessions", "")),
            order_165_cell,
            pm("flightMode", row.get("flightMode", "")),
            pm("geolocation", row.get("geolocation", "")),
            pm("restrictedDocs", row.get("restrictedDocs", "")),
            "-",
        ]
        ws.append(report_row)

    # Авто-ширина колонок
    for col_idx, header in enumerate(report_header, start=1):
        max_len = len(str(header))
        for row_cells in ws.iter_rows(min_row=2, min_col=col_idx, max_col=col_idx):
            for cell in row_cells:
                if cell.value is not None:
                    max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 2, 60)

    save_path = filedialog.asksaveasfilename(
        title="Зберегти звіт МКП",
        defaultextension=".xlsx",
        initialfile="phone_report_v2.xlsx",
        filetypes=[("Excel файл", "*.xlsx")],
    )
    if not save_path:
        return

    try:
        wb.save(save_path)
    except Exception as e:
        messagebox.showerror("Помилка", f"Не вдалося зберегти звіт:\n{e}")
        return

    messagebox.showinfo("Готово", f"Звіт збережено:\n{save_path}\n\nСирі дані взято з: {csv_path}")