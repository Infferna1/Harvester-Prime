import socket
import psutil
import pythoncom
import win32com.client
import wmi


def is_random_mac(mac: str) -> bool:
    # Check if Mac is Locally Administered (Random Mac)
    if not mac or mac in ("N/A", "Unknown"):
        return False

    parts = mac.split(":")
    if len(parts) != 6:
        return False

    first_byte = parts[0]
    if len(first_byte) != 2:
        return False

    second_nibble = first_byte[1].upper()
    return second_nibble in {"2", "6", "A", "E"}


def _get_active_route_ip():
    """
    IP інтерфейсу, через який ОС зараз реально маршрутизує трафік, через WMI:
    беремо дефолтний маршрут (Destination/Mask "0.0.0.0",
    найменший Metric1 - як у виводі "route print") з Win32_IP4RouteTable,
    дістаємо його InterfaceIndex, і вже по ньому - IP з Win32_NetworkAdapterConfiguration.
    Це той самий COM/WMI механізм, що і для Win32_NetworkAdapter нижче, жодного
    зовнішнього процесу чи мережевого пакету. Повертає None, якщо
    дефолтного маршруту немає (мережі взагалі немає).
    """
    try:
        wmi_net = win32com.client.GetObject("winmgmts:root\\cimv2")
        routes = list(wmi_net.ExecQuery(
            "SELECT InterfaceIndex, Metric1 FROM Win32_IP4RouteTable "
            "WHERE Destination='0.0.0.0' AND Mask='0.0.0.0'"
        ))
        if not routes:
            return None
        best_route = min(routes, key=lambda r: r.Metric1)

        configs = list(wmi_net.ExecQuery(
            f"SELECT IPAddress FROM Win32_NetworkAdapterConfiguration "
            f"WHERE InterfaceIndex={best_route.InterfaceIndex}"
        ))
        if not configs or not configs[0].IPAddress:
            return None

        return next((ip for ip in configs[0].IPAddress if ip and ":" not in ip), None)
    except Exception:
        return None


def collect_info_via_libraries():
    def is_virtual_string(s):
        if not s:
            return False
        s = s.lower()
        virtual_keywords = [
            "virtual", "vmware", "hyper-v", "loopback", "host-only",
            "tunnel", "bridge", "bluetooth", "vpn", "default switch",
            "nat", "pseudo-interface", "container", "vethernet"
        ]
        return any(keyword in s for keyword in virtual_keywords)

    info = {
        "Hostname": "",
        "BIOS_Serial": "",
        "IP": "",
        "StaticMAC": "NA",
        "RandomMAC": "NA",
        "ConnectionType": "",
        "Description": ""
    }

    try:
        info["Hostname"] = socket.gethostname()
    except Exception:
        info["Hostname"] = "Unknown"

    try:
        c = wmi.WMI()
        bios = c.Win32_BIOS()[0]
        sn = bios.SerialNumber.strip()
        info["BIOS_Serial"] = sn if sn else "Unknown"
    except Exception:
        info["BIOS_Serial"] = "Unknown"

    try:
        interfaces = psutil.net_if_addrs()
        stats = psutil.net_if_stats()

        wmi_net = win32com.client.GetObject("winmgmts:root\\cimv2")
        wmi_adapters = wmi_net.ExecQuery("SELECT * FROM Win32_NetworkAdapter WHERE NetConnectionStatus=2")

        netconnid_to_desc = {}
        for adapter in wmi_adapters:
            if adapter.NetConnectionID:
                netconnid_to_desc[adapter.NetConnectionID] = adapter.Description or ""

        candidates = []
        for iface_name, addrs in interfaces.items():
            iface_stats = stats.get(iface_name)
            if not iface_stats or not iface_stats.isup:
                continue

            if is_virtual_string(iface_name):
                continue

            ip_addr = None
            mac_addr = None
            for addr in addrs:
                if addr.family == socket.AF_INET:
                    ip_addr = addr.address
                elif addr.family == psutil.AF_LINK:
                    mac_addr = addr.address.replace('-', ':')

            if not ip_addr or not mac_addr:
                continue

            desc = netconnid_to_desc.get(iface_name, "")

            if is_virtual_string(desc):
                continue

            candidates.append({
                "Name": iface_name,
                "IP": ip_addr,
                "MAC": mac_addr,
                "Description": desc
            })

        # Спершу пробуємо визначити, який інтерфейс ОС РЕАЛЬНО зараз
        # використовує для виходу в мережу (а не вгадуємо за назвою) -
        # через дефолтний маршрут із WMI (_get_active_route_ip, без
        # жодного сокета). Знайдену IP шукаємо серед вже відфільтрованих
        # candidates.
        selected = None
        active_ip = _get_active_route_ip()
        if active_ip:
            selected = next((c for c in candidates if c["IP"] == active_ip), None)

        # Fallback (якщо трюк не спрацював - немає мережі взагалі, чи IP
        # не збіглась із жодним candidate) - стара логіка за пріоритетом
        # назви: Ethernet -> Wi-Fi -> перший активний невіртуальний.
        if not selected:
            for c in candidates:
                if "ethernet" in c["Name"].lower() or "ethernet" in c["Description"].lower():
                    selected = c
                    break

        if not selected:
            for c in candidates:
                if "wi-fi" in c["Name"].lower() or "wi-fi" in c["Description"].lower() or "wifi" in c["Name"].lower() or "wifi" in c["Description"].lower() or "wlan" in c["Name"].lower() or "wlan" in c["Description"].lower():
                    selected = c
                    break

        if not selected and candidates:
            selected = candidates[0]

        if selected:
            info["IP"] = selected["IP"]
            info["MAC"] = selected["MAC"]
            info["Description"] = selected["Description"]
            info["ConnectionType"] = "Ethernet" if "ethernet" in selected["Name"].lower() or "ethernet" in selected["Description"].lower() else "Wi-Fi"
        else:
            info["IP"] = "N/A"
            info["MAC"] = "N/A"
            info["Description"] = "N/A"
            info["ConnectionType"] = "N/A"

    except Exception:
        info["IP"] = "N/A"
        info["MAC"] = "N/A"
        info["Description"] = "N/A"
        info["ConnectionType"] = "N/A"

    mac = info.get("MAC", "")

    if mac and mac not in ("N/A", "Unknown"):
        if is_random_mac(mac):
            info["RandomMAC"] = mac
            info["StaticMAC"] = "NA"
        else:
            info["StaticMAC"] = mac
            info["RandomMAC"] = "NA"
    else:
        info["StaticMAC"] = "NA"
        info["RandomMAC"] = "NA"

    return info


def collect_system_info():
    """
    ЄДИНИЙ шлях збору даних - через нативні бібліотеки Python (socket,
    psutil, wmi, win32com.client), без жодного виклику cmd.exe чи
    powershell.exe.

    ВАЖЛИВО: цю функцію в form_gui.py викликають з фонового потоку
    (threading.Thread), а wmi/win32com.client вимагають, щоб COM був
    ініціалізований (CoInitialize) саме в тому потоці, де їх
    використовують - без цього wmi.WMI()/win32com.client.GetObject()
    мовчки падають у except, і в результаті все виходить
    "Unknown"/"N/A". Тому ініціалізуємо COM тут явно, на початку
    функції, і звільняємо після завершення.
    """
    pythoncom.CoInitialize()
    try:
        return collect_info_via_libraries()
    finally:
        pythoncom.CoUninitialize()