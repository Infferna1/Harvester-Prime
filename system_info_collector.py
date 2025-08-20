import subprocess
import json
import socket
import psutil
import win32com.client
import wmi
import re

def can_use_console():
    try:
        proc = subprocess.run(
            ["cmd.exe", "/c", "ipconfig /all"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        return proc.returncode == 0 and bool(proc.stdout.strip())
    except Exception:
        return False

def run_powershell_command(cmd):
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW
        )
        if completed.returncode == 0:
            return completed.stdout.strip()
        else:
            return ""
    except Exception:
        return ""

def collect_info_via_console():
    info = {
        "Hostname": "",
        "BIOS_Serial": "",
        "IP": "",
        "MAC": "",
        "ConnectionType": "",
        "Description": ""
    }

    info["Hostname"] = run_powershell_command("hostname")

    bios_sn_cmd = "Get-CimInstance Win32_BIOS | Select-Object -ExpandProperty SerialNumber"
    bios_sn = run_powershell_command(bios_sn_cmd)
    info["BIOS_Serial"] = bios_sn if bios_sn else "Unknown"

    adapters_cmd = r'''
    Get-NetAdapter -Physical | 
    Where-Object {
        $_.Status -eq "Up" -and
        ($_.HardwareInterface -eq $true) -and
        ($_.InterfaceDescription -notmatch 'virtual|vmware|hyper-v|loopback|host-only|tunnel|bridge|bluetooth|vpn')
    } | Select-Object InterfaceDescription, MacAddress, Status, Name | ConvertTo-Json
    '''
    adapters_json = run_powershell_command(adapters_cmd)

    try:
        adapters = json.loads(adapters_json)
        if isinstance(adapters, dict):
            adapters = [adapters]
    except json.JSONDecodeError:
        adapters = []

    ipconfig_output = run_powershell_command("ipconfig /all")

    def find_ip_for_adapter(adapter_name):
        pattern = re.compile(rf"{re.escape(adapter_name)}.*?IPv4 Address.*?:\s*([\d\.]+)", re.DOTALL | re.IGNORECASE)
        match = pattern.search(ipconfig_output)
        if match:
            return match.group(1)
        return None

    selected_adapter = None
    for adapter in adapters:
        name = adapter.get("Name", "")
        mac = adapter.get("MacAddress", "").replace('-', ':')
        desc = adapter.get("InterfaceDescription", "")
        ip = find_ip_for_adapter(name)

        if ip:
            info["IP"] = ip
            info["MAC"] = mac
            info["Description"] = desc
            info["ConnectionType"] = "Ethernet" if "ethernet" in name.lower() or "ethernet" in desc.lower() else "Wi-Fi"
            selected_adapter = adapter
            break

    if not selected_adapter:
        info["IP"] = "N/A"
        info["MAC"] = "N/A"
        info["Description"] = "N/A"
        info["ConnectionType"] = "N/A"

    return info

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
        "MAC": "",
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

        selected = None
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

    return info

def collect_system_info():
    if can_use_console():
        return collect_info_via_console()
    else:
        return collect_info_via_libraries()
