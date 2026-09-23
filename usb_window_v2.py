import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import csv
import os
import re
import glob
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from config_normalizer import resource_path, load_types_from_json, add_copy_paste_bindings

try:
    from openpyxl import Workbook
except ImportError:
    Workbook = None


# Окрема тека конфігів для USB 2.0, щоб зміни тут не зачіпали стару
# USB-гілку (usb_window.py / usb_filter_window.py та їхні конфіги
# в Data/ConfigData/UsbData).
CONFIG_DIR = "Data/ConfigData/UsbDataVer2"


def open_text_file(file_path):
    """Читає файл повністю, пробуючи utf-8, потім cp1251."""
    for encoding in ("utf-8", "cp1251"):
        try:
            with open(file_path, "r", encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError(
        "unknown", b"", 0, 1, f"Не вдалося визначити кодування файлу: {file_path}"
    )


class USBWindowV2(tk.Toplevel):
    """
    USB 2.0 — нове вікно, незалежне від старого USBWindow.

    Наразі 5 кнопок:
      - Відфільтрувати теку              -> аналог usb_csv_folder_collector.py, але
                                             викликається з GUI і читає файли паралельно
      - Конвертувати журнал (Excel→CSV)  -> аналог convert_excel_to_csv зі старого
                                             USB CSV Collector, але зберігає всі 4
                                             колонки журналу МНІ, а не тільки перші 2
      - Ідентифікувати ЗНІ                -> аналог USBFilterWindow._get_s_level_from_second_file,
                                             винесено в окремий метод для подальшого
                                             розширення формату журналу МНІ
      - Додати ресурси                    -> вибір "Список ПК" (collected_data.csv),
                                             "Тека з USB" (по CSV на кожен ПК) та
                                             "Ідентифікований журнал ЗНІ" (результат
                                             кроку 4); обрані ресурси видно в блоці
                                             "Обрані ресурси"
      - Згенерувати звіт                  -> фінальний Excel за зразком користувача:
                                             № з/п / Пункт / Найменування ЗНІ / Серійний
                                             номер ЗНІ / Інвентарний номер / Відповідальна
                                             особа / Дата останнього підключення /
                                             Перевірено групою / Наявність інформації /
                                             Примітки
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.title("USB 2.0")
        self.geometry("450x420")
        self.transient(parent)
        self.grab_set()

        self.usb_folder = ""
        self.pc_list = []
        self.pc_list_path = ""             # шлях до обраного "Список ПК"
        self.filtered_result_path = ""     # результат "Відфільтрувати теку"
        self.journal_csv_path = ""         # результат "Конвертувати журнал"
        self.identified_result_path = ""   # результат "Ідентифікувати ЗНІ" (авто, після запуску кроку)
        self.identified_journal_rows = []  # дані з ресурсу "Ідентифікований журнал ЗНІ"
        self.identified_journal_path = ""  # шлях до ресурсу "Ідентифікований журнал ЗНІ"

        self._build_ui()

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="USB 2.0", font=("Segoe UI", 12, "bold")).pack(pady=(0, 15))

        btn_opts = {"width": 30}
        ttk.Button(frame, text="Відфільтрувати теку", command=self.filter_folder, **btn_opts).pack(pady=5)
        ttk.Button(frame, text="Журнал ЗНІ (Excel → CSV)", command=self.convert_journal_excel, **btn_opts).pack(pady=5)
        ttk.Button(frame, text="Ідентифікувати ЗНІ", command=self.identify_zni, **btn_opts).pack(pady=5)
        ttk.Button(frame, text="Додати ресурси", command=self.add_resources, **btn_opts).pack(pady=5)
        ttk.Button(frame, text="Згенерувати звіт", command=self.generate_report, **btn_opts).pack(pady=5)

        # Текстове поле, що показує, які ресурси (Список ПК / Тека з USB)
        # наразі обрані — оновлюється кожного разу, коли ресурс додається
        # через "Додати ресурси".
        ttk.Label(frame, text="Обрані ресурси:", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(15, 0))
        self.resources_var = tk.StringVar(value=self._resources_summary())
        ttk.Label(frame, textvariable=self.resources_var, anchor="w", justify="left", wraplength=380).pack(
            fill="x", pady=(2, 0)
        )

        self.status_var = tk.StringVar(value="Тека не обрана")
        ttk.Label(frame, textvariable=self.status_var, anchor="w", wraplength=380, justify="left").pack(
            fill="x", pady=(10, 0)
        )

    def _resources_summary(self):
        pc_line = (
            f"Список ПК: {os.path.basename(self.pc_list_path)} ({len(self.pc_list)} записів)"
            if self.pc_list_path
            else "Список ПК: не обрано"
        )
        usb_line = f"Тека з USB: {self.usb_folder}" if self.usb_folder else "Тека з USB: не обрано"
        journal_line = (
            f"Ідентифікований журнал ЗНІ: {os.path.basename(self.identified_journal_path)} "
            f"({len(self.identified_journal_rows)} записів)"
            if self.identified_journal_path
            else "Ідентифікований журнал ЗНІ: не обрано"
        )
        return f"{pc_line}\n{usb_line}\n{journal_line}"

    def _refresh_resources_display(self):
        self.resources_var.set(self._resources_summary())

    def _set_status(self, text):
        self.status_var.set(text)
        self.update_idletasks()

    # ------------------------------------------------------ 1. Фільтрація

    def filter_folder(self):
        """
        Те саме, що робить usb_csv_folder_collector.py (фільтрація CSV з теки
        за device_types + видалення дублів за серійником), але:
          - викликається прямо з GUI, без окремого запуску скрипта;
          - файли читаються паралельно (ThreadPoolExecutor) — на великих
            теках це помітно швидше за послідовне читання через pandas;
          - без друку в консоль на кожен рядок (лишень підсумкові логи).
        """
        folder_path = filedialog.askdirectory(title="Оберіть теку з CSV для фільтрації")
        if not folder_path:
            return
        self.usb_folder = folder_path

        try:
            config = load_types_from_json(f"{CONFIG_DIR}/usb_types.json")
        except Exception as e:
            messagebox.showerror("Помилка", f"Не вдалося прочитати usb_types.json:\n{e}")
            return

        device_types = {t.strip().lower() for t in config.get("device_types", [])}
        if not device_types:
            messagebox.showerror("Помилка", "У usb_types.json відсутній або порожній 'device_types'.")
            return

        csv_files = glob.glob(os.path.join(folder_path, "*.csv"))
        if not csv_files:
            messagebox.showinfo("Фільтр", "У обраній теці не знайдено CSV-файлів.")
            return

        self._set_status(f"Обробка {len(csv_files)} файлів...")

        def process_file(filepath):
            local_rows = []
            content = None
            for encoding in ("utf-8", "cp1251"):
                try:
                    with open(filepath, "r", encoding=encoding, newline="") as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue
            if content is None:
                return local_rows

            reader = csv.reader(content.splitlines())
            for rec in reader:
                if len(rec) < 3:
                    continue
                if rec[1].strip().lower() in device_types:
                    local_rows.append((rec[0].strip(), rec[1].strip(), rec[2].strip()))
            return local_rows

        seen_serials = set()
        rows_out = []

        with ThreadPoolExecutor(max_workers=min(8, len(csv_files))) as pool:
            for local_rows in pool.map(process_file, csv_files):
                for device, dtype, serial in local_rows:
                    if serial in seen_serials:
                        continue
                    seen_serials.add(serial)
                    rows_out.append((device, dtype, serial))

        if not rows_out:
            messagebox.showinfo("Фільтр", "Не знайдено жодного відповідного запису.")
            self._set_status("Готово: 0 записів")
            return

        result_folder = os.path.join(os.getcwd(), "result")
        os.makedirs(result_folder, exist_ok=True)
        output_path = os.path.join(result_folder, "usb_result_v2.csv")

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Device", "Type", "SerialNumber"])
            writer.writerows(rows_out)

        self.filtered_result_path = output_path
        self._set_status(f"Відфільтровано {len(rows_out)} записів -> {output_path}")
        messagebox.showinfo("Готово", f"Збережено {len(rows_out)} записів у:\n{output_path}")

    # --------------------------------------- 2. Конвертація журналу Excel→CSV

    def convert_journal_excel(self):
        """
        Аналог convert_excel_to_csv зі старого USB CSV Collector скрипта,
        але той лишав тільки перші 2 колонки (df.iloc[:, :2]) — тепер журнал
        МНІ має 4: Серійний номер; sLevel; Інвентарний номер; Відповідальна
        особа, тож беремо всі 4 і пишемо їх у CSV через ';', як і раніше.
        """
        try:
            import pandas as pd
        except ImportError:
            messagebox.showerror(
                "Помилка",
                "Не встановлено бібліотеку pandas.\nВстанови: pip install pandas openpyxl",
            )
            return

        xlsx_path = filedialog.askopenfilename(
            title="Оберіть Excel файл журналу МНІ",
            filetypes=[("Excel files", "*.xlsx *.xls")],
        )
        if not xlsx_path:
            return

        try:
            df = pd.read_excel(xlsx_path, header=None, dtype=str)
        except ImportError:
            messagebox.showerror("Помилка", "Встановіть бібліотеку openpyxl:\n  pip install openpyxl")
            return
        except Exception as e:
            messagebox.showerror("Помилка читання файлу", str(e))
            return

        df = df.iloc[:, :4].dropna(how="all")
        df = df.apply(lambda col: col.str.strip('"').str.strip("'").str.strip() if col.dtype == object else col)
        df = df[df.iloc[:, 0].astype(str).str.strip() != ""]

        # Доповнюємо порожніми колонками, якщо в файлі їх менше 4
        # (напр. ще не встигли дописати інвентарний номер / відповідальну особу)
        for i in range(df.shape[1], 4):
            df[i] = ""

        csv_path = filedialog.asksaveasfilename(
            title="Куди зберегти CSV журналу",
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv")],
            initialfile="journal_mni.csv",
        )
        if not csv_path:
            return

        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            for _, row in df.iterrows():
                values = ["" if pd.isna(row.iloc[i]) else str(row.iloc[i]) for i in range(4)]
                f.write(";".join(values) + "\n")

        self.journal_csv_path = csv_path
        self._set_status(f"Журнал сконвертовано ({len(df)} рядків) -> {csv_path}")
        messagebox.showinfo("Готово", f"CSV журналу збережено:\n{csv_path}\nРядків: {len(df)}")

    # ----------------------------------------------- 3. Ідентифікація ЗНІ

    def identify_zni(self):
        """
        Зіставляє серійні номери з журналом МНІ (як старий
        _get_s_level_from_second_file), результат зіставлення винесено
        в окремі методи (_load_journal / _match_s_level), щоб легко
        підлаштувати під розширений формат журналу, коли він буде готовий.
        """
        source_initialdir = os.path.dirname(self.filtered_result_path) if self.filtered_result_path else None
        source_path = filedialog.askopenfilename(
            title="Оберіть CSV з відфільтрованими серійними номерами",
            filetypes=[("CSV Files", "*.csv")],
            initialdir=source_initialdir,
            initialfile=os.path.basename(self.filtered_result_path) if self.filtered_result_path else "",
        )
        if not source_path:
            return

        journal_initialdir = os.path.dirname(self.journal_csv_path) if self.journal_csv_path else None
        journal_path = filedialog.askopenfilename(
            title="Оберіть журнал МНІ (CSV)",
            filetypes=[("CSV Files", "*.csv")],
            initialdir=journal_initialdir,
            initialfile=os.path.basename(self.journal_csv_path) if self.journal_csv_path else "",
        )
        if not journal_path:
            return

        try:
            type_map = load_types_from_json(f"{CONFIG_DIR}/usb_columns_config.json").get("sLevel", {})
        except Exception as e:
            messagebox.showerror("Помилка", f"Не вдалося прочитати usb_columns_config.json:\n{e}")
            return

        if not type_map:
            messagebox.showerror("Помилка", "У usb_columns_config.json відсутній ключ 'sLevel'.")
            return

        try:
            journal_rows = self._load_journal(journal_path)
        except Exception as e:
            messagebox.showerror("Помилка", f"Не вдалося прочитати журнал МНІ:\n{e}")
            return

        with open(source_path, "r", encoding="utf-8", newline="") as f:
            source_rows = list(csv.DictReader(f))

        results = []
        for row in source_rows:
            serial = row.get("SerialNumber", "").strip()
            match = self._match_journal_row(serial, journal_rows, type_map)
            row = dict(row)
            row.pop("Type", None)  # Type у результаті ідентифікації не потрібен
            results.append({
                **row,
                "sLevel": match["s_level"],
                "InventoryNumber": match["inventory_number"],
                "ResponsiblePerson": match["responsible_person"],
            })

        result_folder = os.path.join(os.getcwd(), "result")
        os.makedirs(result_folder, exist_ok=True)
        output_path = os.path.join(result_folder, "usb_identified_v2.csv")

        fieldnames = list(results[0].keys()) if results else [
            "Device", "SerialNumber", "sLevel", "InventoryNumber", "ResponsiblePerson"
        ]
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
            writer.writeheader()
            writer.writerows(results)

        self.identified_result_path = output_path
        self._set_status(f"Ідентифіковано {len(results)} записів -> {output_path}")
        messagebox.showinfo("Готово", f"Збережено {len(results)} записів у:\n{output_path}")

    def _load_journal(self, journal_path):
        """
        Журнал МНІ, поточний формат (без заголовків, ';'-роздільник):
            Серійний номер; sLevel; Інвентарний номер; Відповідальна особа

        Повертає список словників з цими 4 полями. Якщо формат журналу
        зміниться знову — правити треба буде лише цей метод.
        """
        content = open_text_file(journal_path)
        reader = csv.reader(content.splitlines(), delimiter=";")
        rows = []
        for row in reader:
            if len(row) < 2:
                continue
            sn = row[0].strip().strip('"').replace("﻿", "")
            s_level_raw = row[1].strip().strip('"') if len(row) > 1 else ""
            inventory_number = row[2].strip().strip('"') if len(row) > 2 else ""
            responsible_person = row[3].strip().strip('"') if len(row) > 3 else ""
            rows.append({
                "sn": sn,
                "s_level_raw": s_level_raw,
                "inventory_number": inventory_number,
                "responsible_person": responsible_person,
            })
        return rows

    def _normalize_s_level(self, raw_value, type_map):
        """
        Приводить сире значення sLevel з журналу до одного з type_map.values().

        1. Спершу пробує точний збіг (без регістру/пробілів) — це очікуваний
           випадок для нового журналу, де sLevel вже прийшов окремою колонкою.
        2. Якщо точного збігу нема — шукає значення sLevel десь усередині
           тексту через regex (старий режим, коли колонка була описом, а не
           чистим значенням). Лишив як fallback, бо формат журналу вже
           змінювався один раз і може змінитись знову.
        """
        raw_value = (raw_value or "").strip()
        unidentified = type_map.get("Неідентифіковано", "Неідентифіковано")
        if not raw_value:
            return unidentified

        for value in type_map.values():
            if value.lower() == raw_value.lower():
                return value

        regex_values = [v for v in type_map.values() if v != "Неідентифіковано"]
        if regex_values:
            regex_pattern = r"(" + "|".join(map(re.escape, regex_values)) + r")"
            match = re.search(regex_pattern, raw_value, re.IGNORECASE)
            if match:
                found_value = match.group(1)
                key = next((k for k, v in type_map.items() if v.lower() == found_value.lower()), None)
                return type_map.get(key, unidentified)

        return unidentified

    def _match_journal_row(self, serial, journal_rows, type_map):
        """
        Знаходить у журналі МНІ рядок, серійний номер якого містить суфікс
        шуканого серійника (як у старій логіці), і повертає sLevel,
        інвентарний номер та відповідальну особу з цього рядка.
        """
        serial = serial.strip()
        suffix = serial[-6:] if len(serial) >= 6 else serial

        unidentified = type_map.get("Неідентифіковано", "Неідентифіковано")
        result = {"s_level": unidentified, "inventory_number": "", "responsible_person": ""}

        if not suffix:
            return result

        for entry in journal_rows:
            if suffix in entry["sn"]:
                result["s_level"] = self._normalize_s_level(entry["s_level_raw"], type_map)
                result["inventory_number"] = entry["inventory_number"]
                result["responsible_person"] = entry["responsible_person"]
                break

        return result

    # --------------------------------------------------- 4. Додати ресурси

    def add_resources(self):
        """
        Відкриває вибір ресурсу: "Список ПК", "Тека з USB" або
        "Ідентифікований журнал ЗНІ" (результат кроку "Ідентифікувати ЗНІ" —
        CSV з колонками sLevel/InventoryNumber/ResponsiblePerson).
        Ресурси лише запам'ятовуються (шлях/дані) на цьому кроці — як саме
        вони зводяться у звіт, буде докручено окремо. Обрані ресурси одразу
        видно в головному вікні USB 2.0, в блоці "Обрані ресурси".
        """
        ResourceSelectionWindowV2(self)

    def load_pc_list(self, file_path):
        try:
            with open(file_path, newline="", encoding="utf-8") as f:
                self.pc_list = list(csv.DictReader(f))
        except UnicodeDecodeError:
            with open(file_path, newline="", encoding="cp1251") as f:
                self.pc_list = list(csv.DictReader(f))
        self.pc_list_path = file_path
        self._refresh_resources_display()
        self._set_status(f"Завантажено список ПК: {os.path.basename(file_path)} ({len(self.pc_list)} записів)")

    def load_identified_journal(self, file_path):
        try:
            with open(file_path, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
        except UnicodeDecodeError:
            with open(file_path, newline="", encoding="cp1251") as f:
                rows = list(csv.DictReader(f))

        expected_cols = {"SerialNumber", "sLevel"}
        if rows and not expected_cols.issubset(rows[0].keys()):
            messagebox.showwarning(
                "Увага",
                "У файлі не знайдено очікуваних колонок (SerialNumber, sLevel).\n"
                "Переконайся, що обрано саме результат кроку 'Ідентифікувати ЗНІ'.",
            )

        self.identified_journal_rows = rows
        self.identified_journal_path = file_path
        self._refresh_resources_display()
        self._set_status(f"Завантажено ідентифікований журнал ЗНІ: {os.path.basename(file_path)} ({len(rows)} записів)")

    def set_usb_folder(self, folder_path):
        self.usb_folder = folder_path
        self._refresh_resources_display()
        self._set_status(f"Тека з USB: {folder_path}")

    # -------------------------------------------------- 5. Звіт (Excel)

    def generate_report(self):
        """
        Формує фінальний Excel-звіт за зразком:

            № з/п | Пункт | Найменування ЗНІ | Серійний номер ЗНІ |
            Інвентарний номер | Відповідальна особа |
            Дата останнього підключення | Перевірено групою |
            Наявність інформації | Примітки

        Зводить усі 3 ресурси з "Додати ресурси":
          - Тека з USB       -> перелік підключень ЗНІ по кожному ПК
                                 (ім'я файлу = серійник ПК)
          - Список ПК        -> серійник ПК -> hostname
          - Ідентифікований
            журнал ЗНІ       -> серійник ЗНІ -> Інвентарний номер / Відповідальна особа
        """
        if not self.usb_folder:
            messagebox.showwarning("Увага", "Спершу обери 'Тека з USB' через кнопку 'Додати ресурси'.")
            return
        if not self.pc_list:
            messagebox.showwarning("Увага", "Спершу обери 'Список ПК' через кнопку 'Додати ресурси'.")
            return
        if not self.identified_journal_rows:
            if not messagebox.askyesno(
                "Увага",
                "Не обрано 'Ідентифікований журнал ЗНІ' — усі ЗНІ будуть позначені "
                "як неідентифіковані ('Перевірено групою' = \"-\"). Продовжити?",
            ):
                return
        if Workbook is None:
            messagebox.showerror(
                "Помилка",
                "Не встановлено бібліотеку openpyxl.\nВстанови: pip install openpyxl",
            )
            return

        punkt = simpledialog.askstring(
            "Пункт", "Введіть значення для колонки 'Пункт' (однакове для всіх рядків звіту):", parent=self
        )
        if punkt is None:
            return

        try:
            device_types = {
                t.strip().lower()
                for t in load_types_from_json(f"{CONFIG_DIR}/usb_types.json").get("device_types", [])
            }
        except Exception as e:
            messagebox.showerror("Помилка", f"Не вдалося прочитати usb_types.json:\n{e}")
            return

        try:
            policy = load_types_from_json(f"{CONFIG_DIR}/pc_type_policy.json")
        except Exception as e:
            messagebox.showerror("Помилка", f"Не вдалося прочитати pc_type_policy.json:\n{e}")
            return

        s_level_order = policy.get("sLevelOrder") or []
        s_level_rank = {name: i for i, name in enumerate(s_level_order)}
        # Неідентифікований/невідомий sLevel -> ранг вище за будь-який реальний
        # рівень (навіть за найвищий "Т"), тож завжди перевищує дозволений
        # максимум і вважається порушенням для будь-якого ПК.
        unknown_rank = len(s_level_order)
        pc_type_max_slevel = policy.get("pcTypeMaxSLevel", {})
        # Для pcType, якого немає в конфізі — найсуворіший (найнижчий) дозволений рівень.
        fallback_max_slevel = s_level_order[0] if s_level_order else None
        fallback_max_rank = 0
        unmapped_pc_types = set()
        invalid_slevel_values = set()

        csv_files = glob.glob(os.path.join(self.usb_folder, "*.csv"))
        if not csv_files:
            messagebox.showinfo("Звіт", "У обраній теці з USB не знайдено CSV-файлів.")
            return

        pc_index = self._build_pc_index()
        journal_index = self._build_identified_journal_index()

        # Групуємо всі підключення по серійнику ЗНІ: назва пристрою (з
        # останнього підключення), остання дата, і для кожного hostname —
        # яким pcType він був (потрібно для перевірки політики допуску).
        devices = {}

        for filepath in csv_files:
            pc_serial = os.path.splitext(os.path.basename(filepath))[0].strip()
            pc_info = pc_index.get(pc_serial.lower())
            hostname = pc_info.get("hostname", "") if pc_info else pc_serial
            pc_type_value = (pc_info.get("pcType") if pc_info else "") or ""

            content = None
            for encoding in ("utf-8", "cp1251"):
                try:
                    with open(filepath, "r", encoding=encoding, newline="") as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue
            if content is None:
                continue

            for rec in csv.reader(content.splitlines()):
                if len(rec) < 3:
                    continue
                device_name = rec[0].strip()
                device_type = rec[1].strip()
                usb_serial = rec[2].strip()
                connected_raw = rec[3].strip() if len(rec) > 3 else ""

                if device_type.lower() not in device_types or not usb_serial:
                    continue

                connected_dt = self._parse_connection_date(connected_raw)

                entry = devices.setdefault(
                    usb_serial, {"device": device_name, "last_date": None, "hostnames": {}}
                )
                if hostname:
                    entry["hostnames"][hostname] = pc_type_value
                if connected_dt and (entry["last_date"] is None or connected_dt > entry["last_date"]):
                    entry["last_date"] = connected_dt
                    entry["device"] = device_name

        if not devices:
            messagebox.showinfo("Звіт", "Не знайдено жодного відповідного запису.")
            return

        # Найновіші підключення — першими (як у зразку).
        ordered_serials = sorted(
            devices.keys(), key=lambda s: devices[s]["last_date"] or datetime.min, reverse=True
        )

        wb = Workbook()
        ws = wb.active
        ws.title = "USB звіт"
        ws.append([
            "№ з/п", "Пункт", "Найменування ЗНІ", "Серійний номер ЗНІ", "Інвентарний номер",
            "Відповідальна особа", "Дата останнього підключення", "Перевірено групою",
            "Наявність інформації", "Примітки",
        ])

        for idx, serial in enumerate(ordered_serials, start=1):
            info = devices[serial]
            journal_entry = journal_index.get(serial)
            matched = bool(journal_entry and (journal_entry.get("InventoryNumber") or "").strip())

            if matched:
                inventory_number = journal_entry["InventoryNumber"]
                responsible_person = journal_entry.get("ResponsiblePerson", "")
                checked = "+"
                device_s_level = (journal_entry.get("sLevel") or "").strip()
            else:
                inventory_number = "Неідентифіковано"
                responsible_person = "Неідентифіковано"
                checked = "-"
                device_s_level = "Неідентифіковано"

            # Порушення допуску: ЗНІ підключався до ПК, який дозволяє sLevel
            # НИЖЧИЙ за фактичний sLevel цього ЗНІ . Неідентифікований ЗНІ
            # (unknown_rank = найвищий+1) завжди перевищує дозволений
            # максимум -> порушення для будь-якого ПК.
            device_rank = s_level_rank.get(device_s_level, unknown_rank)
            violating_hosts = []
            for host, pc_type_value in info["hostnames"].items():
                if pc_type_value and pc_type_value not in pc_type_max_slevel:
                    unmapped_pc_types.add(pc_type_value)
                allowed_s_level = pc_type_max_slevel.get(pc_type_value, fallback_max_slevel)
                if allowed_s_level not in s_level_rank:
                    # Значення в pcTypeMaxSLevel не збігається (з урахуванням
                    # регістру) з жодним з sLevelOrder — типова одруківка
                    # (напр. "н/т" замість "Н/Т"). Фіксуємо, щоб попередити
                    # користувача, і про всяк випадок трактуємо найсуворіше.
                    invalid_slevel_values.add(f"{pc_type_value!r} -> {allowed_s_level!r}")
                allowed_rank = s_level_rank.get(allowed_s_level, fallback_max_rank)
                if device_rank > allowed_rank:
                    violating_hosts.append(host)

            if violating_hosts:
                note = "Виявлено підключення до АРМ " + ", ".join(sorted(violating_hosts))
            else:
                note = "-"

            ws.append([
                idx, punkt, info["device"], serial, inventory_number,
                responsible_person, info["last_date"], checked, "-", note,
            ])

        for row_idx in range(2, ws.max_row + 1):
            cell = ws[f"G{row_idx}"]  # Дата останнього підключення
            if isinstance(cell.value, datetime):
                cell.number_format = "dd.mm.yyyy"

        for col_cells in ws.columns:
            width = max((len(str(c.value)) if c.value is not None else 0) for c in col_cells) + 2
            ws.column_dimensions[col_cells[0].column_letter].width = width

        result_folder = os.path.join(os.getcwd(), "result")
        os.makedirs(result_folder, exist_ok=True)
        output_path = filedialog.asksaveasfilename(
            initialdir=result_folder,
            initialfile="usb_report.xlsx",
            defaultextension=".xlsx",
            filetypes=[("Excel Files", "*.xlsx")],
            title="Зберегти звіт як",
        )
        if not output_path:
            return

        wb.save(output_path)
        self._set_status(f"Звіт збережено -> {output_path} ({len(ordered_serials)} записів)")

        info_msg = f"Звіт збережено:\n{output_path}\nЗаписів: {len(ordered_serials)}"
        if unmapped_pc_types:
            info_msg += (
                f"\n\nУвага: у pc_type_policy.json не знайдено ці pcType (застосовано "
                f"найсуворіший рівень '{fallback_max_slevel}'):\n" + ", ".join(sorted(unmapped_pc_types))
            )
        if invalid_slevel_values:
            info_msg += (
                "\n\nУвага: у pcTypeMaxSLevel є значення, які не збігаються (з урахуванням "
                f"регістру) з жодним з sLevelOrder {s_level_order} — ймовірно одруківка "
                "(застосовано найсуворіший рівень):\n" + "\n".join(sorted(invalid_slevel_values))
            )
        messagebox.showinfo("Готово", info_msg)

    def _build_pc_index(self):
        """
        Індекс 'серійник ПК (нижній регістр) -> рядок зі списку ПК',
        будується з self.pc_list (collected_data.csv, поле 'sn').
        """
        index = {}
        for row in self.pc_list:
            sn = (row.get("sn") or "").strip().lower()
            if sn:
                index[sn] = row
        return index

    def _build_identified_journal_index(self):
        """
        Індекс 'серійник ЗНІ -> рядок з ідентифікованого журналу',
        будується з self.identified_journal_rows (usb_identified_v2.csv).
        """
        index = {}
        for row in self.identified_journal_rows:
            serial = (row.get("SerialNumber") or "").strip()
            if serial:
                index[serial] = row
        return index

    def _parse_connection_date(self, raw_value):
        """
        Парсить дату підключення з CSV теки USB. Формат у прикладах —
        '08.08.2025 15:23:39', але про всяк випадок пробує і без часу.
        """
        raw_value = (raw_value or "").strip()
        if not raw_value:
            return None
        for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y"):
            try:
                return datetime.strptime(raw_value, fmt)
            except ValueError:
                continue
        return None


class ResourceSelectionWindowV2(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Який ресурс додати?")
        self.geometry("300x190")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        btn_opts = {"width": 26}
        ttk.Button(self, text="Список ПК", command=self.select_pc, **btn_opts).pack(pady=5)
        ttk.Button(self, text="Тека з USB", command=self.select_folder, **btn_opts).pack(pady=5)
        ttk.Button(
            self, text="Ідентифікований журнал ЗНІ", command=self.select_identified_journal, **btn_opts
        ).pack(pady=5)

    def select_pc(self):
        file_path = filedialog.askopenfilename(
            title="Оберіть CSV файл зі списком ПК",
            filetypes=[("CSV Files", "*.csv")],
        )
        if file_path:
            self.master.load_pc_list(file_path)
        self.destroy()

    def select_identified_journal(self):
        file_path = filedialog.askopenfilename(
            title="Оберіть ідентифікований журнал ЗНІ (результат 'Ідентифікувати ЗНІ')",
            filetypes=[("CSV Files", "*.csv")],
        )
        if file_path:
            self.master.load_identified_journal(file_path)
        self.destroy()

    def select_folder(self):
        folder_path = filedialog.askdirectory(title="Оберіть теку з USB")
        if folder_path:
            self.master.set_usb_folder(folder_path)
        self.destroy()