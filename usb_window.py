import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import csv
import os
from usb_filter_window import USBFilterWindow
from datetime import datetime, timedelta
import json


class USBWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("USB")
        self.transient(parent)
        self.grab_set()

        # Перемінні для збереження даних
        self.usb_data = []  # Для переліку USB
        self.pc_list = []  # Для списку комп'ютерів
        self.usb_folder = ""  # Для теки з USB
        self.usb_file_path = ""  # шлях до файлу з переліком USB
        self.pc_file_path = ""  # шлях до файлу зі списком ПК

        lbl_frame = ttk.Frame(self)
        lbl_frame.pack(fill="x", padx=10, pady=10)

        self.entry_vars = []

        self.texts = self.load_texts("Data/ConfigData/UsbData/usb_default_text.json")
        if self.texts is None:
            self.destroy()
            return

        self.resource_texts = self.load_texts("Data/ConfigData/UsbData/usb_errors.json")
        if self.resource_texts is None:
            self.destroy()
            return

        self.usb_labels = self.load_simple_texts("Data/ConfigData/UsbData/usb_labels.json")
        if self.usb_labels is None:
            self.destroy()
            return

        self.column_types = self.load_texts("Data/ConfigData/UsbData/usb_result_file_types.json")
        if self.column_types is None:
            self.destroy()
            return

        # Завантаження текстів з JSON

        # 1.:
        frame1 = ttk.Frame(lbl_frame)
        frame1.pack(fill="x", pady=5)
        ttk.Label(frame1, text=self.texts["line1_part1"]).pack(side="left")
        var1 = tk.StringVar()
        self.entry_vars.append(var1)
        ttk.Entry(frame1, textvariable=var1, width=6).pack(side="left", padx=2)
        ttk.Label(frame1, text=self.texts["line1_part2"]).pack(side="left")
        var2 = tk.StringVar()
        self.entry_vars.append(var2)
        ttk.Entry(frame1, textvariable=var2, width=6).pack(side="left", padx=2)
        ttk.Label(frame1, text=self.texts["line1_part3"]).pack(side="left")

        # 2.:
        frame2 = ttk.Frame(lbl_frame)
        frame2.pack(fill="x", pady=5)
        ttk.Label(frame2, text=self.texts["line2_part1"]).pack(side="left")
        var3 = tk.StringVar()
        self.entry_vars.append(var3)
        ttk.Entry(frame2, textvariable=var3, width=6).pack(side="left", padx=2)
        ttk.Label(frame2, text=self.texts["line2_part2"]).pack(side="left")

        # 3.:
        frame3 = ttk.Frame(lbl_frame)
        frame3.pack(fill="x", pady=5)
        ttk.Label(frame3, text=self.texts["line3_part1"]).pack(side="left")
        var4 = tk.StringVar()
        self.entry_vars.append(var4)
        ttk.Entry(frame3, textvariable=var4, width=6).pack(side="left", padx=2)
        ttk.Label(frame3, text=self.texts["line3_part2"]).pack(side="left")
        var5 = tk.StringVar()
        self.entry_vars.append(var5)
        ttk.Entry(frame3, textvariable=var5, width=6).pack(side="left", padx=2)
        ttk.Label(frame3, text=self.texts["line3_part3"]).pack(side="left")

        # Таблиця
        try:
            with open("Data/ConfigData/UsbData/usb_columns_config.json", "r", encoding="utf-8") as f:
                cols = json.load(
                    f)
            with open("Data/ConfigData/UsbData/usb_rows_types.json", "r", encoding="utf-8") as f:
                row_definitions = json.load(f)
                rows = list(row_definitions.keys())  # ключі — назви рядків
        except Exception as e:
            messagebox.showerror("Помилка", f"Не вдалося завантажити конфігурацію таблиці: {e}")
            row_definitions = {}

        main_col = list(cols.keys())[0]
        sub_cols_map = cols[main_col]

        # Визначаємо колонки: перший стовпець — main_col, потім ключі словника (назви для таблиці)
        columns = [main_col] + list(sub_cols_map.keys())

        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=6)

        for col in columns:
            self.tree.heading(col, text=col)
            if col == main_col:
                self.tree.column(col, width=140, anchor=tk.W)
            else:
                self.tree.column(col, width=140, anchor=tk.CENTER)

        # Додавання рядків: для кожного рядка створюємо пусті значення у стовпцях (крім головного)
        for row in rows:
            self.tree.insert("", tk.END, values=(row,) + ("",) * (len(columns) - 1))

        self.tree.pack(fill="both", expand=True, padx=10, pady=10)

        # Збереження row_definitions для подальшого використання, якщо потрібно
        self.row_definitions = row_definitions

        # Панель з новими кнопками та полем "Дата перевірки"
        bottom_frame = ttk.Frame(self)
        bottom_frame.pack(fill="x", padx=10, pady=(0, 10))

        # Кнопки
        btn_filter = ttk.Button(bottom_frame, text="Відфільтрувати USB", command=self.filter_usb)
        btn_filter.pack(side="left", padx=5)

        btn_add = ttk.Button(bottom_frame, text="Додати ресурси", command=self.add_resources)
        btn_add.pack(side="left", padx=5)

        # Поле з лейблом
        ttk.Label(bottom_frame, text="Дата перевірки:").pack(side="left", padx=(20, 5))
        # Створюємо поле дати перевірки та заповнюємо поточною датою
        self.check_date_var = tk.StringVar(value=datetime.now().strftime("%d.%m.%Y"))
        ttk.Entry(bottom_frame, textvariable=self.check_date_var, width=12).pack(side="left", padx=5)

        # Кнопка "Розрахувати"
        btn_calc = ttk.Button(bottom_frame, text="Розрахувати", command=self.calculate)
        btn_calc.pack(side="left", padx=20)


        # Лейбли для вибраних файлів/тек
        self.file_label_usb = ttk.Label(self, text=self.resource_texts.get("u_file_not_selected"), anchor="w")
        self.file_label_usb.pack(fill="x", padx=10, pady=5)

        self.file_label_pc = ttk.Label(self, text=self.resource_texts.get("p_file_not_selected"), anchor="w")
        self.file_label_pc.pack(fill="x", padx=10, pady=5)

        self.folder_label_usb = ttk.Label(self, text=self.resource_texts.get("u_folder_not_selected"), anchor="w")
        self.folder_label_usb.pack(fill="x", padx=10, pady=5)


    def add_resources(self):
        # Відкриваємо вікно з вибором ресурсу
        resource_window = ResourceSelectionWindow(self)
        self.wait_window(resource_window)


    def load_pc_list(self):
        file_path = filedialog.askopenfilename(
            title="Оберіть CSV файл для Списку ПК",
            filetypes=[("CSV Files", "*.csv")],
        )
        if not file_path:
            return

        # Зчитуємо ПК дані через dict_reader
        a_data = []
        for encoding in ("utf-8", "cp1251"):
            try:
                with open(file_path, newline='', encoding=encoding) as f:
                    reader = csv.DictReader(f)
                    a_data = list(reader)
                print(f"Дані з файлу {file_path} прочитані як словники, рядків: {len(a_data)}")
                break
            except Exception as e:
                print(f"Помилка при зчитуванні даних з ПК файлу {file_path} з кодуванням {encoding}: {e}")

        if a_data:
            self.pc_list = a_data
            self.file_label_pc.config(text=f"Список ПК: {os.path.basename(file_path)}")
            self.pc_file_path = file_path
        else:
            messagebox.showerror("Помилка", "Не вдалося зчитати дані з файлу.")


    def load_usb_list(self):
        file_path = filedialog.askopenfilename(
            title="Оберіть CSV файл для Переліку USB",
            filetypes=[("CSV Files", "*.csv")],
        )
        if not file_path:
            return

        file_name = os.path.basename(file_path)

        usb_data = self._read_usb_csv(file_path)
        if usb_data:
            self.usb_data = usb_data
            self.file_label_usb.config(text=f"Перелік USB: {file_name}")
            print(f"Дані з файлу {file_name} успішно завантажені.")
            self.usb_file_path = file_path
        else:
            messagebox.showerror("Помилка", "Не вдалося зчитати дані з файлу.")


    def load_usb_folder(self):
        folder_path = filedialog.askdirectory(title="Оберіть теку з USB")
        if not folder_path:
            return
        self.usb_folder = folder_path
        self.folder_label_usb.config(text=f"Тека з USB: {folder_path}")
        print(f"Тека з USB: {folder_path}")

        usb_dict = {}

        for filename in os.listdir(folder_path):
            filepath = os.path.join(folder_path, filename)
            if os.path.isfile(filepath) and filename.endswith('.csv'):
                computer_serial = filename.rsplit('.', 1)[0]

                # Читання CSV з fallback кодуванням
                rows = self._read_csv_with_fallback_encoding(filepath)

                for row in rows:
                    if len(row) >= 2:
                        flash_serial = row[0].strip()
                        g = row[1].strip()
                        usb_dict[flash_serial] = (g, computer_serial, "Невідомо")

        self.usb_data = usb_dict
        print(f"usb_dict сформовано, записів: {len(usb_dict)}")


    def _read_usb_csv(self, file_path):
        usb_data = []
        try:
            with open(file_path, newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) >= 2:
                        usb_data.append(row)  # Зберігаємо увесь рядок
        except Exception as e:
            print(f"Помилка при зчитуванні CSV файлу: {e}")
        return usb_data


    def filter_usb(self):
        USBFilterWindow(self)


    def _read_csv_with_fallback_encoding(self, file_path, dict_mode=False):
        data = []
        for encoding in ("utf-8", "cp1251"):
            try:
                print(f"Спроба відкрити файл {file_path} з кодуванням {encoding}")
                with open(file_path, newline='', encoding=encoding) as f:
                    if dict_mode:
                        reader = csv.DictReader(f)
                    else:
                        reader = csv.reader(f)
                    data = list(reader)
                print(f"Успішно прочитано {file_path} з кодуванням {encoding}, рядків: {len(data)}")
                break
            except UnicodeDecodeError:
                print(f"Не вдалося відкрити файл {file_path} з кодуванням {encoding}")
            except Exception as e:
                print(f"Помилка при зчитуванні файлу {file_path}: {e}")
        return data


    def load_keys(self):
        import json
        with open("Data/ConfigData/UsbData/usb_pc_info.json", "r", encoding="utf-8") as f:
            return json.load(f)

    def calculate(self):
        print("Початок збору інформації з теки USB...")

        if not self.usb_folder:
            messagebox.showwarning("Увага", "Не обрано теку з USB файлами.")
            return

        # Завантажуємо device_types з usb_types.json для фільтрації csv-файлів
        try:
            with open("Data/ConfigData/UsbData/usb_types.json", "r", encoding="utf-8") as f:
                usb_filter_config = json.load(f)
            device_types = set([t.strip().lower() for t in usb_filter_config.get("device_types", [])])
            print(f"Дозволені типи пристроїв з usb_types.json (після обробки): {device_types}")
        except Exception as e:
            messagebox.showerror("Помилка", f"Не вдалося зчитати usb_types.json: {e}")
            return

        # Завантажуємо конфігурацію для підрахунків і таблиць
        counts, device_types, usb_rows_types, cols, rows, type_map = self.load_config_and_init_counts()

        if device_types is None:
            messagebox.showerror("Помилка", "Не вдалося завантажити конфігурацію для підрахунків.")
            return

        keys = self.load_keys()
        results = []

        for filename in os.listdir(self.usb_folder):
            filepath = os.path.join(self.usb_folder, filename)

            if not (os.path.isfile(filepath) and filename.lower().endswith(".csv")):
                continue

            computer_serial = os.path.splitext(filename)[0].strip()

            file_loaded = False

            for encoding in ("utf-8", "cp1251"):
                try:
                    with open(filepath, "r", encoding=encoding) as f:
                        reader = csv.reader(f)
                        for row in reader:
                            if len(row) < 4:
                                continue

                            device_name = row[0].strip()
                            device_type = row[1].strip().lower()  # Переводимо в нижній регістр
                            serial = row[2].strip()
                            last_date = row[3].strip()

                            # Перевіряємо тип пристрою
                            print(f"Перевірка типу пристрою: '{device_type}'")

                            # Фільтруємо по типу пристрою з usb_types.json
                            if device_type not in device_types:
                                print(f"  Пропускаємо пристрій з типом '{device_type}' — не в списку дозволених типів")
                                continue

                            # Пошук ПК по серійному номеру
                            found = None
                            for pc in self.pc_list:
                                for sn_key in keys["serial_numbers"]:
                                    sn_value = pc.get(sn_key, "").strip()
                                    if sn_value.lower() == computer_serial.lower():
                                        found = pc
                                        break
                                if found:
                                    break

                            if not found:
                                print(
                                    f"  НЕ знайдено АРМ для серійного номера '{computer_serial}' серед keys: {keys['serial_numbers']}")
                            else:
                                print(
                                    f"  Знайдено АРМ для серійного номера '{computer_serial}': ПК тип '{found.get(keys['pc_type'], 'Невідомо')}', Hostname '{found.get(keys['host'], 'Невідомо')}', Мережа '{found.get(keys['net'], 'Невідомо')}'")

                            a_info = found

                            pc_type = a_info.get(keys["pc_type"], "Невідомо") if a_info else "Невідомо"
                            hostname = a_info.get(keys["host"], "Невідомо") if a_info else "Невідомо"
                            network = a_info.get(keys["net"], "Невідомо") if a_info else "Невідомо"

                            results.append([
                                device_name, device_type, serial, last_date,
                                computer_serial, pc_type, hostname, network
                            ])
                    print(f"Файл {filename} прочитано з кодуванням {encoding}")
                    file_loaded = True
                    break
                except UnicodeDecodeError as e:
                    print(f"Не вдалося прочитати {filename} з кодуванням {encoding}: {e}")
                except Exception as e:
                    print(f"Інша помилка при читанні {filename}: {e}")

            if not file_loaded:
                print(f"Файл {filename} не вдалося прочитати жодним із відомих кодувань.")

        if not results:
            messagebox.showinfo("Результат", "Не знайдено жодного пристрою з дозволеними типами.")
            return

        # Завантажуємо mapping для серійних номерів
        serial_to_g = self.load_g_mapping()
        self.save_final_csv(results, serial_to_g)

        print("allowed_types_counts перед викликом filter_and_count_by_date:", device_types)

        # Фільтруємо за датою та записуємо результат
        self.filter_and_count_by_date(output_path="Data/usb_pc_thing1.csv",
                                      usb_rows_types=usb_rows_types,
                                      type_map=type_map,
                                      cols=cols,
                                      rows=rows)


    def load_g_mapping(self):
        serial_to_g = {}
        if self.usb_file_path and os.path.exists(self.usb_file_path):
            try:
                for encoding in ("utf-8", "cp1251"):
                    try:
                        with open(self.usb_file_path, "r", encoding=encoding) as f:
                            reader = csv.reader(f)
                            for row in reader:
                                if len(row) >= 2:
                                    serial = row[0].strip()
                                    g = row[1].strip()
                                    serial_to_g[serial] = g
                        print(f"Інформація успішно прочитана з {self.usb_file_path}")
                        break
                    except UnicodeDecodeError:
                        continue
            except Exception as e:
                print(f"Помилка при читанні {self.usb_file_path}: {e}")
        else:
            print("Файл переліку не знайдено. Неможливо опрацювати перелік.")
        return serial_to_g

    def save_final_csv(self, results, sn_to_g):
        data_folder = os.path.join(os.getcwd(), "result")  # створюємо шлях до папки "result" відносно скрипта
        if not os.path.exists(data_folder):
            os.makedirs(data_folder)  # створюємо папку, якщо її немає

        output_path = os.path.join(data_folder, "usb_pc_result.csv")

        try:
            with open(output_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f, quoting=csv.QUOTE_ALL)
                writer.writerow([
                    self.column_types.get("type1"),
                    self.column_types.get("type2"),
                    self.column_types.get("type3"),
                    self.column_types.get("type4"),
                    self.column_types.get("type5"),
                    self.column_types.get("type6"),
                    self.column_types.get("type7"),
                    self.column_types.get("type8"),
                    self.column_types.get("type9")
                ])
                for row in results:
                    serial = row[2]
                    g = sn_to_g.get(serial, "неідентифіковано")
                    writer.writerow(row + [g])

            messagebox.showinfo("Готово", f"Файл usb_pc_thing.csv створено ({len(results)} записів).")
        except Exception as e:
            messagebox.showerror("Помилка запису", f"Не вдалося записати файл: {e}")


    def load_config_and_init_counts(self):
        # Завантаження типів з usb_types.json
        try:
            with open("Data/ConfigData/UsbData/usb_types.json", "r", encoding="utf-8") as f:
                usb_filter_config = json.load(f)
                allowed_device_types = set([t.strip().lower() for t in usb_filter_config.get("device_types", [])])
                print("allowed_device_types із usb_types.json:", allowed_device_types)
        except Exception as e:
            print(f"Не вдалося завантажити usb_types.json: {e}")
            return None, None, None, None, None, None

        # Завантаження rows types з usb_rows_types.json
        try:
            with open("Data/ConfigData/UsbData/usb_rows_types.json", "r", encoding="utf-8") as f:
                usb_rows_types = json.load(f)
                rows = list(usb_rows_types.keys())
        except Exception as e:
            print(f"Не вдалося завантажити usb_rows_types.json: {e}")
            return None, None, None, None, None, None

        # Завантаження columns з usb_columns_config.json
        try:
            with open("Data/ConfigData/UsbData/usb_columns_config.json", "r", encoding="utf-8") as f:
                usb_columns_config = json.load(f)
                type_map = usb_columns_config.get("sLevel", {})
                cols = usb_columns_config # Idk what to do with this :C
#TODO: Figure out what this ^^^^^ code do ASAP >:(
        except Exception as e:
            print(f"Не вдалося завантажити usb_columns_config.json: {e}")
            return None, None, None, None, None, None

        # Ініціалізація counts на основі rows і allowed_device_types
        counts = {row_type: {dev_type: 0 for dev_type in allowed_device_types} for row_type in usb_rows_types.keys()}

        return counts, allowed_device_types, usb_rows_types, cols, rows, type_map


    #TODO: Fix
    def filter_and_count_by_date(self, output_path, usb_rows_types, type_map, cols, rows):

        # Перетворюємо дату та визначаємо проміжок
        check_date = datetime.strptime(self.check_date_var.get(), "%d.%m.%Y")
        start_date = check_date - timedelta(days=10)

        counts = {pc: {code: 0 for code in type_map.values()} for pc in rows}

        # Для унікальних серійників по кожному ПК
        seen_serials_per_pc = {pc: set() for pc in rows}

        # Читаємо CSV з результатами
        with open(output_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                pc_type_row = row.get("pcType", "").strip()
                network_row = row.get("network", "").strip()
                serial = row.get("serialNumber", "").strip()
                s_level_raw = row.get("sLevel", "Неідентифіковано")
                s_level_raw = s_level_raw.strip().strip('"')  # прибираємо лапки, якщо вони є
                device_code = type_map.get(s_level_raw, type_map.get("Неідентифіковано"))

                # DEBUG
                print(f"[DEBUG] serial: {serial}, s_level_raw: {s_level_raw}, device_code: {device_code}")

                # Фільтруємо по даті
                try:
                    connect_date = datetime.strptime(row["connectionDate"], "%d.%m.%Y %H:%M:%S")
                except (ValueError, KeyError):
                    continue
                if not (start_date <= connect_date <= check_date):
                    continue

                # Визначаємо категорію ПК
                matched_category = None
                for category, data in usb_rows_types.items():
                    pc_variants = [p.strip() for p in data.get("pc_types", [])]
                    net_variants = [n.strip() for n in data.get("network_types", [])]
                    if pc_type_row in pc_variants and (not net_variants or network_row in net_variants):
                        matched_category = category
                        break
                if not matched_category:
                    continue

                # Перевірка унікальності серійника
                if serial in seen_serials_per_pc[matched_category]:
                    continue
                seen_serials_per_pc[matched_category].add(serial)

                counts[matched_category][device_code] += 1

        # --- Підрахунок статистики ---
        unidentified_code = "Неідентифіковано"
        total_drives = sum(
            dev_dict.get(code, 0) for dev_dict in counts.values() for code in type_map.values())
        unidentified_count = sum(dev_dict.get(unidentified_code, 0) for dev_dict in counts.values())
        percent_unidentified = round((unidentified_count / total_drives) * 100) if total_drives else 0
        total_reg = total_drives - unidentified_count
        percent_reg = round((total_reg / total_drives) * 100) if total_drives else 0

        # --- Очищення Treeview ---
        for item in self.tree.get_children():
            self.tree.delete(item)

        # --- Додавання нових значень у Treeview ---
        main_col = list(cols.keys())[0]
        col_map = cols[main_col]  # {"Тип1": "Тип1", "Тип2": "Тип2", ...}
        usb_types_list = list(col_map.keys())  # список типів флешок

        for pc_type in rows:
            row_values = [pc_type]
            for col in usb_types_list:
                code = col_map[col]
                row_values.append(counts.get(pc_type, {}).get(code, 0))
            self.tree.insert("", "end", values=row_values)

        # --- Оновлення Entry поля статистики ---
        self.entry_vars[0].set(str(unidentified_count))
        self.entry_vars[1].set(str(percent_unidentified))
        self.entry_vars[2].set(str(total_drives))
        self.entry_vars[3].set(str(total_reg))
        self.entry_vars[4].set(str(percent_reg))


    def load_texts(self, path, required_keys=None):
        try:
            with open(path, "r", encoding="utf-8") as file:
                data = json.load(file)

                if required_keys:
                    missing = [key for key in required_keys if key not in data]
                    if missing:
                        raise KeyError(f"Відсутні ключі у JSON: {', '.join(missing)}")

                return data
        except Exception as e:
            messagebox.showerror("Помилка", f"Не вдалося завантажити файл з текстами:\n{path}\n\n{e}")
            return None


    def load_simple_texts(self, path):
        try:
            with open(path, "r", encoding="utf-8") as file:
                return json.load(file)
        except Exception as e:
            messagebox.showerror("Помилка", f"Не вдалося завантажити файл з текстами:\n{path}\n\n{e}")
            return None


class ResourceSelectionWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Який ресурс додати?")
        self.geometry("300x150")
        self.resizable(False, False)

        button_width = 20
        ttk.Button(self, text="Перелік USB", command=self.select_usb, width=button_width).pack(pady=5)
        ttk.Button(self, text="Список ПК", command=self.select_pc, width=button_width).pack(pady=5)
        ttk.Button(self, text="Тека з USB", command=self.select_folder, width=button_width).pack(pady=5)


    def select_usb(self):
        self.master.load_usb_list()
        self.destroy()


    def select_pc(self):
        self.master.load_pc_list()
        self.destroy()


    def select_folder(self):
        self.master.load_usb_folder()
        self.destroy()
