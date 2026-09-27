import tkinter as tk
from tkinter import ttk

from phone_window_v2 import PhoneWindowV2
from usb_window_v2 import USBWindowV2
from pc_window_v2 import PcWindowV2

# Стара форма (поля Тип ПК/Мережа/Hostname/S/N/IP/MAC/Відділ/Власник/Agent ID/
# логічні параметри + "Зберегти дані") та старі кнопки "Додати МКП"/"USB"
# прибрані з головного вікна за прямою вимогою користувача - тепер тут
# лишається лише хаб із трьома кнопками. Сам функціонал (phone_window.py,
# usb_window.py, старий save_data/collected_data.csv) нікуди не зникає -
# просто вже не викликається звідси.


class App(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Harvester-Prime")
        self.resizable(False, False)

        self.create_widgets()

    def create_widgets(self):
        frame = ttk.Frame(self, padding=30)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Harvester-Prime", font=("Segoe UI", 14, "bold")).pack(pady=(0, 20))

        btn_args = {"width": 20}

        ttk.Button(frame, text="АРМ", command=self.on_pc_v2_click, **btn_args).pack(pady=8)
        ttk.Button(frame, text="МКП", command=self.on_phone_v2_click, **btn_args).pack(pady=8)
        ttk.Button(frame, text="USB", command=self.on_usb_v2_click, **btn_args).pack(pady=8)

    def on_pc_v2_click(self):
        add_win = PcWindowV2(self)
        add_win.grab_set()

    def on_phone_v2_click(self):
        add_win = PhoneWindowV2(self)
        add_win.grab_set()

    def on_usb_v2_click(self):
        add_win = USBWindowV2(self)
        add_win.grab_set()


if __name__ == "__main__":
    app = App()
    app.mainloop()