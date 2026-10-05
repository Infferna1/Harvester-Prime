import csv
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog

from config_normalizer import load_types_from_json, calculateNextNumber, add_copy_paste_bindings, format_mac_address
from system_info_collector import collect_system_info

# Окрема тека конфігів для ПК 2.0, щоб зміни тут не зачіпали стару
# гілку (form_gui.py та її конфіги в Data/ConfigData/).
CONFIG_DIR = "Data/ConfigData/PcData"

# pc_types.json - СПІЛЬНИЙ зі старою формою файл (Data/ConfigData/, а не
# PcData/) - "Категорія АРМ" має показувати ті самі значення, що й старе
# "Тип ПК" у form_gui.py, тож свідомо не дублюємо цей конфіг.
PC_TYPES_PATH = "Data/ConfigData/pc_types.json"


def _get_app_dir():
    """
    Тека, де фізично лежить .exe (PyInstaller) або цей .py файл (розробка) -
    НЕ поточна робоча тека (os.getcwd()), яка залежить від способу запуску.
    Дані (CSV) зберігаємо саме тут, щоб застосунок завжди знаходив свій
    файл, незалежно від того, як його запустили.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CSV_FILENAME = os.path.join(_get_app_dir(), "collected_pc_data_v2.csv")

IP_ALLOWED_CHARS = set("0123456789.-")


def format_ip_address(obj, var, entry, formatting_flag_name: str):
    """
    IP-адреса не завжди чиста IPv4 (255.255.255.255) - тож НЕ нав'язуємо
    групи по 3 цифри й обмеження в 255. Просто не даємо ввести нічого,
    крім цифр і "." / "-" (IP_ALLOWED_CHARS) - решту відкидаємо.
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

        filtered = "".join(ch for ch in raw if ch in IP_ALLOWED_CHARS)

        if filtered != raw:
            var.set(filtered)
            new_cursor = min(len(filtered), cursor + (len(filtered) - len(raw)))
            try:
                entry.icursor(new_cursor)
            except Exception:
                pass
    finally:
        obj.after_idle(lambda: setattr(obj, formatting_flag_name, False))


def _load_csv_fields_order():
    return load_types_from_json(f"{CONFIG_DIR}/csv_fields_order.json")["fields"]


def _load_report_header():
    return load_types_from_json(f"{CONFIG_DIR}/report_header.json")["header"]


# ЄДИНИЙ fallback для presence_labels.json - раніше в різних місцях коду
# (створення тумблера, перевірка "Стороннє ПЗ", формування звіту) були різні
# запасні значення ("Присутнє" в одному місці, "Виявлено" в іншому), тож при
# відсутності ключа в JSON кнопка малювалась з одним текстом, а перевірка
# натискання звірялась з іншим - вони не збігались, і поле вводу не
# активувалось. Тепер fallback лише тут, і викликається звідусіль.
DEFAULT_PRESENCE_LABELS = {"positive": "Присутнє", "negative": "Відсутнє"}


def _get_presence_labels(presence_labels_dict, field_key):
    return presence_labels_dict.get(field_key, DEFAULT_PRESENCE_LABELS)


class PcWindowV2(tk.Toplevel):
    """
    ПК 2.0 (хаб) - новий, окремий від старої форми збору ПК (яка лишається
    головним вікном form_gui.py повністю без змін). Два кроки: "Додати ПК"
    (одна картка ПК, дописується в collected_pc_data_v2.csv) та
    "Згенерувати звіт" (підсумковий .xlsx за зразком).
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.title("ПК 2.0")
        self.resizable(False, False)

        frame = ttk.Frame(self, padding=20)
        frame.pack()

        ttk.Label(frame, text="ПК 2.0", font=("Segoe UI", 12, "bold")).pack(pady=(0, 15))

        ttk.Button(frame, text="Додати ПК", width=25, command=self.open_add_window).pack(pady=5)
        ttk.Button(frame, text="Згенерувати звіт", width=25, command=self.generate_report).pack(pady=5)
        ttk.Button(frame, text="Закрити", width=25, command=self.destroy).pack(pady=(15, 0))

    def open_add_window(self):
        add_win = PcEntryWindowV2(self)
        add_win.grab_set()

    def generate_report(self):
        generate_pc_report_v2(self)


class PcEntryWindowV2(tk.Toplevel):
    """Форма введення однієї картки ПК (2.0)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Введення даних щодо ПК (2.0)")
        self.parent = parent

        self.field_names = load_types_from_json(f"{CONFIG_DIR}/pc_field_names.json")
        self.presence_labels = load_types_from_json(f"{CONFIG_DIR}/presence_labels.json")
        self.pc_types = load_types_from_json(PC_TYPES_PATH)
        self.pc_type_values = list(self.pc_types.values()) if self.pc_types else ["-"]

        spz_config = load_types_from_json(f"{CONFIG_DIR}/spz_pc_options.json")
        self.spz_options = spz_config.get("options", ["-"])
        restricted_software_config = load_types_from_json(f"{CONFIG_DIR}/restricted_software_options.json")
        self.restricted_software_options = restricted_software_config.get("options", ["-"])

        self.armType_var = tk.StringVar(value="Службовий")
        self.toggle_vars = {}
        self.spz_check_vars = {}

        self.create_widgets()

        threading.Thread(target=self._load_system_info_async, daemon=True).start()

    # --- автозбір Hostname/IP/MAC/RandomMAC/S/N (той самий колектор, що і в старій формі) ---
    def _load_system_info_async(self):
        info = collect_system_info()
        self.after(0, self._apply_system_info, info)

    def _apply_system_info(self, info):
        self.hostname_var.set(info.get("Hostname", ""))
        self.sn_var.set(info.get("BIOS_Serial", ""))
        self.ip_var.set(info.get("IP", ""))
        self.mac_var.set(info.get("StaticMAC", ""))
        self.random_mac_var.set(info.get("RandomMAC", ""))

        for entry in (self.hostname_entry, self.sn_entry):
            entry.config(state="normal")
            add_copy_paste_bindings(entry)

    # --- допоміжне створення toggle-полів (Присутнє/Відсутнє тощо) ---
    def _make_toggle(self, parent, row, label_text, field_key, command=None, column=0, columnspan=2, label_width=None):
        """
        Підпис і обидві радіокнопки живуть в ОДНОМУ Frame (pack), і саме
        цей Frame гридиться як єдине ціле. Так підпис завжди впритул до
        своїх кнопок, незалежно від того, наскільки широкі поля в інших
        рядках форми (раніше підпис і кнопки були в різних колонках
        спільної сітки, і через це "розповзались" при зміні ширини
        сусідніх полів).

        label_width (у символах) - якщо задано, підпис отримує фіксовану
        ширину (вирівняний по лівому краю, з "хвостом" пробілів). Це дає
        групі полів з однаковим label_width варіанти відповіді на ОДНІЙ
        відстані від початку рядка, навіть якщо самі тексти підписів різної
        довжини. Групи з різним label_width між собою не вирівнюються -
        це й треба.
        """
        labels = _get_presence_labels(self.presence_labels, field_key)
        var = tk.StringVar(value=labels["negative"])
        self.toggle_vars[field_key] = var

        frame = ttk.Frame(parent)
        frame.grid(row=row, column=column, columnspan=columnspan, sticky="w", padx=5, pady=3)
        label_kwargs = {"width": label_width} if label_width is not None else {}
        ttk.Label(frame, text=label_text, **label_kwargs).pack(side="left")
        ttk.Radiobutton(frame, text=labels["positive"], variable=var,
                         value=labels["positive"], command=command).pack(side="left", padx=(10, 5))
        ttk.Radiobutton(frame, text=labels["negative"], variable=var,
                         value=labels["negative"], command=command).pack(side="left", padx=5)
        return var

    def create_widgets(self):
        # Реальна ширина форми (довгі підписи toggle-полів + широкі entry/
        # combobox) більша за старі 760px - через це права частина (S/N,
        # Random MAC і все, що в колонках 2-3) обрізалась за межу видимої
        # області, бо горизонтального скролу не було. Тепер: ширший canvas
        # (1050) + горизонтальний scrollbar як страховка на майбутнє.
        canvas_frame = ttk.Frame(self)
        canvas_frame.pack(fill="both", expand=True)
        canvas = tk.Canvas(canvas_frame, width=750, height=850, highlightthickness=0)
        v_scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        h_scrollbar = ttk.Scrollbar(canvas_frame, orient="horizontal", command=canvas.xview)
        canvas.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)

        body = ttk.Frame(canvas, padding=10)
        canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        row = 0

        # Кожен блок нижче - ОДИН самодостатній Frame (підпис + поле/кнопки
        # разом, через pack), гриджений в body як єдине ціле. Поля на одному
        # рядку (Hostname/S/N, MAC/Random MAC) - це два окремі такі Frame-и
        # в column=0 і column=1. Завдяки цьому ширина одного поля ніколи не
        # "розсуває" підпис і поле в іншому рядку - вони завжди разом.

        # ЄДИНА ширина підпису для УСІХ toggle-полів форми (Авторизація,
        # Заявка на підключення ... Несанкціоноване підключення) - раніше
        # це були окремі групи з різною шириною, тепер все вирівняно в один
        # спільний стовпець варіантів відповіді. Значення взяте з
        # найдовшого підпису форми ("Несанкціоноване підключення до мережі
        # Інтернет:").
        TOGGLE_LABEL_WIDTH = 28

        # Тип АРМ: Службовий / Особистий
        type_frame = ttk.Frame(body)
        type_frame.grid(row=row, column=0, columnspan=2, sticky="w", padx=5, pady=5)
        ttk.Label(type_frame, text="Тип АРМ:").pack(side="left")
        ttk.Radiobutton(type_frame, text="Службовий", variable=self.armType_var, value="Службовий").pack(side="left", padx=(10, 5))
        ttk.Radiobutton(type_frame, text="Особистий", variable=self.armType_var, value="Особистий").pack(side="left", padx=5)
        row += 1

        # Категорія АРМ - зі списку pc_types.json
        cat_frame = ttk.Frame(body)
        cat_frame.grid(row=row, column=0, columnspan=2, sticky="w", padx=5, pady=5)
        ttk.Label(cat_frame, text="Категорія АРМ:").pack(side="left")
        self.pcCategory_var = tk.StringVar(value=self.pc_type_values[0])
        self.pcCategory_combo = ttk.Combobox(
            cat_frame, textvariable=self.pcCategory_var, values=self.pc_type_values, state="readonly", width=90
        )
        self.pcCategory_combo.pack(side="left", padx=(10, 0))
        row += 1

        self._make_toggle(body, row, "Авторизація:", "authorization", label_width=TOGGLE_LABEL_WIDTH); row += 1

        # Hostname / IP-адреса / MAC-адреса - підписи мають ОДНАКОВУ фіксовану
        # ширину (GROUP1_LABEL_WIDTH), тож самі текстові поля стартують на
        # однаковій відстані від початку рядка, незалежно від довжини
        # конкретного підпису. S/N і Random MAC - на своїх рядках поруч,
        # у це вирівнювання свідомо не включені (про них мова не йшла).
        GROUP1_LABEL_WIDTH = 12

        # Hostname / S/N (автозбір, як у старій формі) - два окремі
        # самодостатні Frame-и поруч в одному рядку (column=0 і column=1).
        host_frame = ttk.Frame(body)
        host_frame.grid(row=row, column=0, sticky="w", padx=5, pady=5)
        ttk.Label(host_frame, text="Hostname:", width=GROUP1_LABEL_WIDTH).pack(side="left")
        self.hostname_var = tk.StringVar()
        self.hostname_entry = ttk.Entry(host_frame, width=25, textvariable=self.hostname_var, state="readonly")
        self.hostname_entry.pack(side="left", padx=(10, 0))

        sn_frame = ttk.Frame(body)
        sn_frame.grid(row=row, column=1, sticky="w", padx=5, pady=5)
        ttk.Label(sn_frame, text="S/N:").pack(side="left")
        self.sn_var = tk.StringVar()
        self.sn_entry = ttk.Entry(sn_frame, width=25, textvariable=self.sn_var, state="readonly")
        self.sn_entry.pack(side="left", padx=(10, 0))
        row += 1

        # IP (автозбір + власний фільтр символів, редагується вручну за потреби)
        ip_frame = ttk.Frame(body)
        ip_frame.grid(row=row, column=0, columnspan=2, sticky="w", padx=5, pady=5)
        ttk.Label(ip_frame, text="IP-адреса:", width=GROUP1_LABEL_WIDTH).pack(side="left")
        self.ip_var = tk.StringVar()
        self.ip_entry = ttk.Entry(ip_frame, width=25, textvariable=self.ip_var)
        self.ip_var.trace_add("write", lambda *args: format_ip_address(self, self.ip_var, self.ip_entry, "_formatting_ip"))
        add_copy_paste_bindings(self.ip_entry)
        self.ip_entry.pack(side="left", padx=(10, 0))
        row += 1

        # MAC / Random MAC (автозбір, існуюче автоформатування MAC не чіпаємо) -
        # так само два окремі Frame-и поруч.
        mac_frame = ttk.Frame(body)
        mac_frame.grid(row=row, column=0, sticky="w", padx=5, pady=5)
        ttk.Label(mac_frame, text="MAC-адреса:", width=GROUP1_LABEL_WIDTH).pack(side="left")
        self.mac_var = tk.StringVar()
        self.mac_entry = ttk.Entry(mac_frame, width=25, textvariable=self.mac_var)
        self.mac_var.trace_add("write", lambda *args: format_mac_address(self, self.mac_var, self.mac_entry, "_formatting_mac"))
        add_copy_paste_bindings(self.mac_entry)
        self.mac_entry.pack(side="left", padx=(10, 0))

        random_mac_frame = ttk.Frame(body)
        random_mac_frame.grid(row=row, column=1, sticky="w", padx=5, pady=5)
        ttk.Label(random_mac_frame, text="Random MAC:").pack(side="left")
        self.random_mac_var = tk.StringVar()
        self.random_mac_entry = ttk.Entry(random_mac_frame, width=25, textvariable=self.random_mac_var)
        self.random_mac_var.trace_add(
            "write", lambda *args: format_mac_address(self, self.random_mac_var, self.random_mac_entry, "_formatting_random_mac")
        )
        add_copy_paste_bindings(self.random_mac_entry)
        self.random_mac_entry.pack(side="left", padx=(10, 0))
        row += 1

        TOGGLE_LABEL_WIDTH2 = 42
        self._make_toggle(body, row, "Заявка на підключення до мережі Інтернет:", "internetRequest", label_width=TOGGLE_LABEL_WIDTH2); row += 1
        self._make_toggle(body, row, "Закріплення ІР-адреси за MAC-адресою:", "ipMacBinding", label_width=TOGGLE_LABEL_WIDTH2); row += 1

        # СПЗ - мультивибір (чекбокси), список може бути довгим (40+ варіантів),
        # тож розбиваємо по SPZ_PER_ROW штук в один рядок замість одного
        # нескінченного горизонтального ряду. Підпис "СПЗ:" і сам блок
        # чекбоксів - в одному зовнішньому Frame, щоб підпис завжди стояв
        # впритул до першого чекбокса.
        SPZ_PER_ROW = 7
        spz_outer = ttk.Frame(body)
        spz_outer.grid(row=row, column=0, columnspan=2, sticky="w", padx=5, pady=5)
        ttk.Label(spz_outer, text="СПЗ:").pack(side="left", anchor="n")
        spz_frame = ttk.Frame(spz_outer)
        spz_frame.pack(side="left", padx=(10, 0))
        for idx, option in enumerate(self.spz_options):
            var = tk.BooleanVar(value=False)
            self.spz_check_vars[option] = var
            spz_row, spz_col = divmod(idx, SPZ_PER_ROW)
            ttk.Checkbutton(spz_frame, text=option, variable=var).grid(
                row=spz_row, column=spz_col, sticky="w", padx=5, pady=2
            )
        row += 1

        self._make_toggle(body, row, "Антивірус (АВКП ESET):", "antivirus", label_width=TOGGLE_LABEL_WIDTH); row += 1
        self._make_toggle(body, row, "HX-агент (EDR):", "hx", label_width=TOGGLE_LABEL_WIDTH); row += 1
        self._make_toggle(body, row, "Закріплення ШПЗ:", "shpzBinding", label_width=TOGGLE_LABEL_WIDTH); row += 1
        self._make_toggle(body, row, "ШПЗ в карантині АВКП ESET:", "shpzQuarantine", label_width=TOGGLE_LABEL_WIDTH); row += 1
        self._make_toggle(body, row, "Ексфільтрація даних:", "exfiltration", label_width=TOGGLE_LABEL_WIDTH); row += 1
        self._make_toggle(body, row, "Порушення обробки:", "processingViolation", label_width=TOGGLE_LABEL_WIDTH); row += 1
        self._make_toggle(body, row, "Політики безпеки:", "policies", label_width=TOGGLE_LABEL_WIDTH); row += 1
        self._make_toggle(body, row, "Контроль ідентифікації ЗНІ:", "control", label_width=TOGGLE_LABEL_WIDTH); row += 1
        self._make_toggle(body, row, "Неліцензійне ПЗ:", "unlicensedSoftware", label_width=TOGGLE_LABEL_WIDTH); row += 1

        # Стороннє (заборонене) ПЗ + список (обрати з готового і/або дописати вручну).
        # self.restricted_software_items - єдине джерело правди (список рядків),
        # Listbox нижче лише відображає його, щоб було видно, що вже додано.
        self.restricted_software_items = []

        self._make_toggle(
            body, row, "Стороннє ПЗ:", "restrictedSoftware",
            command=self._on_restricted_software_change, label_width=TOGGLE_LABEL_WIDTH
        )
        row += 1

        # "Яке саме" - підпис + combobox + кнопка "Додати" разом в одному Frame.
        pick_frame = ttk.Frame(body)
        pick_frame.grid(row=row, column=0, columnspan=2, sticky="w", padx=5, pady=5)
        ttk.Label(pick_frame, text="Яке саме:").pack(side="left")
        self.restricted_software_combo = ttk.Combobox(
            pick_frame, values=self.restricted_software_options, width=27, state="disabled"
        )
        self.restricted_software_combo.pack(side="left", padx=(10, 5))
        self.restricted_software_combo.bind("<Return>", lambda e: self._add_selected_restricted_software())
        self.restricted_software_add_btn = ttk.Button(
            pick_frame, text="Додати", command=self._add_selected_restricted_software, width=15, state="disabled"
        )
        self.restricted_software_add_btn.pack(side="left", padx=5)
        row += 1

        # "Вже додано" - підпис + Listbox + скрол + кнопка "Видалити" разом.
        added_frame = ttk.Frame(body)
        added_frame.grid(row=row, column=0, columnspan=2, sticky="w", padx=5, pady=5)
        ttk.Label(added_frame, text="Вже додано:").pack(side="left", anchor="n")
        self.restricted_software_listbox = tk.Listbox(
            added_frame, width=45, height=4, state="disabled", exportselection=False
        )
        self.restricted_software_listbox.pack(side="left", padx=(10, 0))
        listbox_scroll = ttk.Scrollbar(added_frame, orient="vertical", command=self.restricted_software_listbox.yview)
        listbox_scroll.pack(side="left", fill="y")
        self.restricted_software_listbox.config(yscrollcommand=listbox_scroll.set)
        self.restricted_software_remove_btn = ttk.Button(
            added_frame, text="Видалити обране", command=self._remove_selected_restricted_software, width=15, state="disabled"
        )
        self.restricted_software_remove_btn.pack(side="left", padx=(10, 0), anchor="n")
        row += 1

        # Case - вільний текст
        case_frame = ttk.Frame(body)
        case_frame.grid(row=row, column=0, columnspan=2, sticky="w", padx=5, pady=5)
        ttk.Label(case_frame, text="Case:").pack(side="left")
        self.case_entry = ttk.Entry(case_frame, width=30)
        add_copy_paste_bindings(self.case_entry)
        self.case_entry.pack(side="left", padx=(10, 0))
        row += 1

        self._make_toggle(body, row, "Несанкціоноване підключення (МКП):", "unauthorizedMkpConnection", label_width=TOGGLE_LABEL_WIDTH); row += 1
        self._make_toggle(body, row, "Несанкціоноване підключення до мережі Інтернет:", "unauthorizedNetworkConnection", label_width=TOGGLE_LABEL_WIDTH); row += 1

        # Кнопки
        btn_frame = ttk.Frame(body)
        btn_frame.grid(row=row, column=0, columnspan=2, pady=15)
        ttk.Button(btn_frame, text="Зберегти", command=self.save_data_to_csv).pack(side="left", padx=10)
        ttk.Button(btn_frame, text="Відміна", command=self.cancel).pack(side="left", padx=10)

        self.protocol("WM_DELETE_WINDOW", self.cancel)

    def _on_restricted_software_change(self):
        labels = _get_presence_labels(self.presence_labels, "restrictedSoftware")
        if self.toggle_vars["restrictedSoftware"].get() == labels["positive"]:
            self.restricted_software_combo.config(state="normal")
            self.restricted_software_add_btn.config(state="normal")
            self.restricted_software_remove_btn.config(state="normal")
            self.restricted_software_listbox.config(state="normal")
        else:
            self.restricted_software_combo.set("")
            self.restricted_software_items.clear()
            self._refresh_restricted_software_listbox()
            self.restricted_software_combo.config(state="disabled")
            self.restricted_software_add_btn.config(state="disabled")
            self.restricted_software_remove_btn.config(state="disabled")
            self.restricted_software_listbox.config(state="disabled")

    def _refresh_restricted_software_listbox(self):
        """Малюємо Listbox заново з self.restricted_software_items - тепер
        видно, що саме вже додано до списку "Стороннє ПЗ", а не лише
        суху строку через кому."""
        prev_state = self.restricted_software_listbox.cget("state")
        self.restricted_software_listbox.config(state="normal")
        self.restricted_software_listbox.delete(0, tk.END)
        for item in self.restricted_software_items:
            self.restricted_software_listbox.insert(tk.END, item)
        self.restricted_software_listbox.config(state=prev_state)

    def _add_selected_restricted_software(self):
        chosen = self.restricted_software_combo.get().strip()
        if not chosen or chosen == "-":
            return
        if chosen not in self.restricted_software_items:
            self.restricted_software_items.append(chosen)
            self._refresh_restricted_software_listbox()
        self.restricted_software_combo.set("")

    def _remove_selected_restricted_software(self):
        selection = self.restricted_software_listbox.curselection()
        if not selection:
            return
        for index in reversed(selection):
            del self.restricted_software_items[index]
        self._refresh_restricted_software_listbox()

    def _toggle_value(self, field_key):
        """
        Безпечний доступ до self.toggle_vars: якщо з якоїсь причини (баг,
        неповний файл, розсинхрон конфігів) конкретний тумблер не був
        створений у create_widgets(), збереження ПК більше не падає з
        KeyError на весь метод collect_data() - просто це одне поле піде
        в CSV як "-" (замість Присутнє/Виявлено/тощо), а решта даних
        збережеться нормально.
        """
        var = self.toggle_vars.get(field_key)
        return var.get() if var is not None else "-"

    def collect_data(self):
        f = self.field_names
        spz_selected = [opt for opt, var in self.spz_check_vars.items() if var.get() and opt != "-"]
        return {
            f["armType"]: self.armType_var.get(),
            f["pcCategory"]: self.pcCategory_var.get(),
            f["authorization"]: self._toggle_value("authorization"),
            f["hostname"]: self.hostname_var.get(),
            f["ip"]: self.ip_var.get(),
            f["mac"]: self.mac_var.get(),
            f["randomMac"]: self.random_mac_var.get(),
            f["sn"]: self.sn_var.get(),
            f["internetRequest"]: self._toggle_value("internetRequest"),
            f["ipMacBinding"]: self._toggle_value("ipMacBinding"),
            f["spz"]: ", ".join(spz_selected),
            f["antivirus"]: self._toggle_value("antivirus"),
            f["hx"]: self._toggle_value("hx"),
            f["shpzBinding"]: self._toggle_value("shpzBinding"),
            f["shpzQuarantine"]: self._toggle_value("shpzQuarantine"),
            f["exfiltration"]: self._toggle_value("exfiltration"),
            f["processingViolation"]: self._toggle_value("processingViolation"),
            f["policies"]: self._toggle_value("policies"),
            f["control"]: self._toggle_value("control"),
            f["unlicensedSoftware"]: self._toggle_value("unlicensedSoftware"),
            f["restrictedSoftware"]: self._toggle_value("restrictedSoftware"),
            f["restrictedSoftwareList"]: ", ".join(self.restricted_software_items),
            f["caseField"]: self.case_entry.get(),
            f["unauthorizedMkpConnection"]: self._toggle_value("unauthorizedMkpConnection"),
            f["unauthorizedNetworkConnection"]: self._toggle_value("unauthorizedNetworkConnection"),
        }

    def save_data_to_csv(self):
        if not self.hostname_var.get().strip():
            messagebox.showwarning("Увага", "Hostname порожній - зачекайте завершення автозбору даних або впишіть вручну.")
            return

        collected = self.collect_data()
        filename = CSV_FILENAME
        file_exists = os.path.isfile(filename) and os.path.getsize(filename) > 0

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
    """
    Читає CSV максимально стійко до того, як саме файл був востаннє
    збережений:
    - "utf-8-sig" йде першим, бо якщо файл відкривали й зберігали в Excel,
      Excel часто дописує BOM на початок - зі звичайним "utf-8" це б не
      ламало читання одразу, але могло псувати ім'я першої колонки
      ("\\ufeffnumberInOrder" замість "numberInOrder"), через що
      DictReader не знаходив потрібні ключі.
    - Роздільник визначається автоматично через csv.Sniffer замість
      жорсткої коми: типова причина "файл ніби є, а рядків 0" - Excel в
      україномовній/європейській локалі при збереженні міняє роздільник
      коми на крапку з комою, і стандартний DictReader тоді бачить кожен
      рядок як ОДНЕ поле замість багатьох, що на практиці часто
      сприймається як "порожньо" далі по коду.
    """
    rows = []
    if not csv_path or not os.path.isfile(csv_path):
        return rows
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            with open(csv_path, "r", encoding=encoding, newline="") as f:
                sample = f.read(4096)
                f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
                except csv.Error:
                    dialect = csv.excel  # стандартна кома, якщо Sniffer не впевнений
                reader = csv.DictReader(f, dialect=dialect)
                rows = list(reader)
            return rows
        except UnicodeDecodeError:
            continue
    return rows


def _to_plus_minus(value, labels):
    positive = labels.get("positive", "")
    return "+" if value == positive else "-"


def generate_pc_report_v2(master):
    try:
        import openpyxl
        from openpyxl.utils import get_column_letter
    except ImportError:
        messagebox.showerror("Помилка", "Бібліотека openpyxl не встановлена.")
        return

    initial_dir = os.path.dirname(CSV_FILENAME) if os.path.isfile(CSV_FILENAME) else _get_app_dir()
    initial_file = os.path.basename(CSV_FILENAME) if os.path.isfile(CSV_FILENAME) else ""
    csv_path = filedialog.askopenfilename(
        title="Оберіть CSV з даними ПК",
        filetypes=[("CSV Files", "*.csv")],
        initialdir=initial_dir,
        initialfile=initial_file,
        parent=master,
    )
    if not csv_path:
        return

    rows = _read_collected_csv(csv_path)
    if not rows:
        file_size = os.path.getsize(csv_path) if os.path.isfile(csv_path) else 0
        if file_size > 0:
            # Файл фізично існує і не пустий, але жодного рядка даних
            # розпізнати не вдалося - найімовірніше, нестандартний
            # роздільник/кодування (наприклад, файл пересимпортовано і
            # пересимпортовано Excel-ом). Показуємо розмір файлу, щоб
            # відрізнити цей випадок від дійсно порожнього/відсутнього файлу.
            messagebox.showwarning(
                "Увага",
                f"Файл {csv_path} не порожній ({file_size} байт), але жодного рядка даних "
                "розпізнати не вдалося. Перевір, що файл дійсно у форматі CSV "
                "(кома, UTF-8/CSV, не пересимпортований Excel-ем з іншим роздільником)."
            )
        else:
            messagebox.showwarning("Увага", f"Файл {csv_path} відсутній або порожній.")
        return

    punkt = simpledialog.askstring("Пункт", "Введіть значення для стовпця «Пункт» (однакове для всього звіту):", parent=master)
    if punkt is None:
        return

    presence_labels = load_types_from_json(f"{CONFIG_DIR}/presence_labels.json")

    def pm(field_key, raw_value):
        labels = _get_presence_labels(presence_labels, field_key)
        return _to_plus_minus(raw_value, labels)

    report_header = _load_report_header()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Звіт"
    ws.append(report_header)

    for idx, row in enumerate(rows, start=1):
        restricted_software_raw = row.get("restrictedSoftware", "")
        restricted_software_mark = pm("restrictedSoftware", restricted_software_raw)
        restricted_software_list = (row.get("restrictedSoftwareList") or "").strip()
        restricted_software_cell = restricted_software_list if (restricted_software_mark == "+" and restricted_software_list) else "-"

        spz_cell = (row.get("spz") or "").strip() or "-"

        case_cell = (row.get("caseField") or "").strip() or "-"

        report_row = [
            idx,
            punkt,
            row.get("armType", ""),
            row.get("pcCategory", ""),
            pm("authorization", row.get("authorization", "")),
            row.get("hostname", ""),
            row.get("ip", ""),
            row.get("mac", ""),
            pm("internetRequest", row.get("internetRequest", "")),
            pm("ipMacBinding", row.get("ipMacBinding", "")),
            spz_cell,
            pm("antivirus", row.get("antivirus", "")),
            pm("hx", row.get("hx", "")),
            pm("shpzBinding", row.get("shpzBinding", "")),
            pm("shpzQuarantine", row.get("shpzQuarantine", "")),
            pm("exfiltration", row.get("exfiltration", "")),
            pm("processingViolation", row.get("processingViolation", "")),
            pm("policies", row.get("policies", "")),
            pm("control", row.get("control", "")),
            pm("unlicensedSoftware", row.get("unlicensedSoftware", "")),
            restricted_software_cell,
            case_cell,
            pm("unauthorizedMkpConnection", row.get("unauthorizedMkpConnection", "")),
            pm("unauthorizedNetworkConnection", row.get("unauthorizedNetworkConnection", "")),
            "-",
        ]
        ws.append(report_row)

    for col_idx, header in enumerate(report_header, start=1):
        max_len = len(str(header))
        for row_cells in ws.iter_rows(min_row=2, min_col=col_idx, max_col=col_idx):
            for cell in row_cells:
                if cell.value is not None:
                    max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 2, 60)

    save_path = filedialog.asksaveasfilename(
        title="Зберегти звіт ПК",
        defaultextension=".xlsx",
        initialfile="pc_report_v2.xlsx",
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