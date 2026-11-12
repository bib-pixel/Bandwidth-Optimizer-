"""Passive Windows Mobile Hotspot adapter and client discovery.

Only reads Windows interface configuration and the ARP cache; it does not scan
or probe devices. ARP entries are incomplete evidence, not a full client list.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
import subprocess
import sys


class HotspotDiscovery:
    def __init__(self, gateway: str | None = None, interface: str | None = None):
        self.hotspot_gateway = gateway or os.getenv("HOTSPOT_GATEWAY", "192.168.137.1")
        self.hotspot_interface = interface or os.getenv("HOTSPOT_INTERFACE", "Local Area Connection* 4")
        try:
            self.network = ipaddress.ip_network(f"{self.hotspot_gateway.rsplit('.', 1)[0]}.0/24", strict=False)
        except ValueError:
            self.network = ipaddress.ip_network("192.168.137.0/24")

    def find_interface(self) -> dict | None:
        """Find the adapter that owns HOTSPOT_GATEWAY, not just a guessed alias."""
        if sys.platform != "win32":
            return None
        command = (
            "$g='" + self.hotspot_gateway.replace("'", "") + "'; "
            "Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | "
            "Where-Object {$_.IPAddress -eq $g} | "
            "Select-Object -First 1 @{Name='InterfaceAlias';Expression={$_.InterfaceAlias}},"
            "@{Name='IPAddress';Expression={$_.IPAddress}},"
            "@{Name='InterfaceIndex';Expression={$_.InterfaceIndex}} | ConvertTo-Json -Compress"
        )
        try:
            result = subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True, text=True, timeout=8, check=False)
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                if isinstance(data, dict) and data.get("InterfaceAlias"):
                    return data
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
            pass
        # Do not pretend the configured fallback was detected as an actual adapter.
        return None

    def clients(self, gateway: str | None = None) -> list[dict]:
        """Return client-like entries already present in the Windows ARP cache."""
        gateway = gateway or self.hotspot_gateway
        if sys.platform != "win32":
            return []
        try:
            result = subprocess.run(["arp", "-a", "-N", gateway], capture_output=True, text=True, timeout=8, check=False)
        except (OSError, subprocess.SubprocessError):
            return []
        devices = []
        for ip, mac, state in re.findall(r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F-]{17})\s+(\w+)", result.stdout):
            try:
                address = ipaddress.ip_address(ip)
            except ValueError:
                continue
            if address not in self.network or ip == gateway or mac.lower().startswith("ff-"):
                continue
            try:
                hostname = socket.gethostbyaddr(ip)[0]
            except (socket.herror, OSError):
                hostname = f"hotspot-client-{ip.rsplit('.', 1)[-1]}"
            devices.append({"ip_address": ip, "mac_address": mac.upper().replace("-", ":"), "hostname": hostname,
                            "vendor": "Unknown", "status": "ARP entry observed", "source": "Windows ARP cache"})
        return devices
