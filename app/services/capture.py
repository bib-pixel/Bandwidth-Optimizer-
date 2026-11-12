"""Live packet capture for a user-selected hotspot/network interface.

Live mode uses Scapy and therefore requires Npcap on Windows plus an elevated
terminal.  Failure is intentionally non-fatal: callers receive simulation mode.
"""

from __future__ import annotations

import logging
import os
import socket
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone

from app.models import Traffic, db
from app.services.classifier import TrafficClassifier

logger = logging.getLogger(__name__)


@dataclass
class CaptureStatus:
    mode: str
    interface: str
    message: str


class NetworkMonitor:
    """Captures a short, bounded window of packets from the chosen interface."""

    def __init__(self) -> None:
        self.mode = "live" if os.getenv("CAPTURE_MODE", "simulation").strip().lower() == "live" else "simulation"
        self.interface = os.getenv("CAPTURE_INTERFACE", "Wi-Fi")
        self.classifier = TrafficClassifier()
        self.hotspot_interface: str | None = None

    def configure(self, mode: str, interface: str) -> CaptureStatus:
        self.mode = "live" if mode == "live" else "simulation"
        self.interface = interface or "Wi-Fi"
        return CaptureStatus(self.mode, self.interface, "Configuration saved.")

    def interfaces(self) -> list[str]:
        """Return friendly Windows adapter names plus Scapy/Npcap interfaces."""
        names = [name for _, name in socket.if_nameindex()]
        try:
            command = "Get-NetAdapter -IncludeHidden | Select-Object -ExpandProperty Name | ConvertTo-Json -Compress"
            result = subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True, text=True, timeout=8, check=False)
            if result.stdout.strip():
                import json
                adapters = json.loads(result.stdout)
                names.extend(adapters if isinstance(adapters, list) else [adapters])
        except Exception as exc:
            logger.debug("Could not enumerate Windows adapters: %s", exc)
        try:
            from scapy.all import IFACES
            names.extend(str(item.name) for item in IFACES.values() if getattr(item, "name", None))
        except Exception as exc:
            logger.debug("Could not enumerate Npcap interfaces: %s", exc)
        return sorted({name.strip() for name in names if name and name.strip()}, key=str.casefold)

    def capture_window(self, seconds: int = 2) -> tuple[list[Traffic], str]:
        """Capture and aggregate actual IPv4 TCP/UDP packets for one window.

        No simulated data is returned from this method.  Each output row is an
        observed flow (source, destination and ports), with its measured Mbps.
        """
        try:
            from scapy.all import IP, TCP, UDP, sniff  # type: ignore
            # Resolve the selected friendly adapter name to a Scapy interface if possible.
            selected = self.interface
            try:
                from scapy.all import IFACES
                matches = [iface for iface in IFACES.values() if selected.casefold() in str(getattr(iface, "name", "")).casefold()]
                if matches:
                    selected = matches[0].name
            except Exception:
                pass
            packets = sniff(iface=selected, timeout=seconds, store=True, filter="ip")
        except Exception as exc:
            logger.warning("Live capture failed on %s: %s", self.interface, exc)
            return [], f"Live capture unavailable on {self.interface}: {exc}. Install Npcap, run as Administrator, and select the adapter carrying the device traffic. No simulated data is shown."

        flows: dict[tuple[str, str, str, int | None, int | None], dict] = {}
        for packet in packets:
            if not packet.haslayer(IP):
                continue
            ip = packet[IP]
            protocol, source_port, destination_port = "IP", None, None
            if packet.haslayer(TCP):
                protocol, source_port, destination_port = "TCP", int(packet[TCP].sport), int(packet[TCP].dport)
            elif packet.haslayer(UDP):
                protocol, source_port, destination_port = "UDP", int(packet[UDP].sport), int(packet[UDP].dport)
            else:
                continue
            key = (ip.src, ip.dst, protocol, source_port, destination_port)
            flow = flows.setdefault(key, {"bytes": 0, "packets": 0})
            flow["bytes"] += len(packet)
            flow["packets"] += 1

        records: list[Traffic] = []
        for (source_ip, destination_ip, protocol, source_port, destination_port), flow in flows.items():
            throughput = flow["bytes"] * 8 / seconds / 1_000_000
            cls = self.classifier.classify(protocol, destination_port or 0, flow["packets"] / seconds, throughput)
            records.append(Traffic(timestamp=datetime.now(timezone.utc), source_ip=source_ip, destination_ip=destination_ip, protocol=protocol, source_port=source_port, destination_port=destination_port, packet_length=flow["bytes"], packet_rate=round(flow["packets"] / seconds, 2), throughput_mbps=round(throughput, 4), upload_ratio=0.5, traffic_type=cls.traffic_type, confidence=cls.confidence))
        return records, f"Captured {len(packets)} packets across {len(records)} actual flows on {self.interface} in the last {seconds} seconds."


monitor = NetworkMonitor()
