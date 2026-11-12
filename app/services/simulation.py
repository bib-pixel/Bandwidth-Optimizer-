"""Realistic traffic simulator used when live capture is not available."""

from __future__ import annotations

import random
from datetime import datetime, timezone

from app.models import ConnectedDevice, Traffic, db
from app.services.classifier import TrafficClassifier


class TrafficSimulator:
    profiles = [
        ("Video Conferencing", "UDP", 3478, (5.0, 16.0), (90, 180)),
        ("Gaming", "UDP", 27015, (1.0, 6.0), (45, 130)),
        ("Streaming", "TCP", 443, (7.0, 25.0), (30, 100)),
        ("Web Browsing", "TCP", 443, (0.2, 3.0), (5, 45)),
        ("File Download", "TCP", 443, (8.0, 28.0), (20, 70)),
        ("Background Updates", "TCP", 443, (0.5, 8.0), (10, 50)),
    ]

    def __init__(self) -> None:
        self.classifier = TrafficClassifier()

    def seed_devices(self) -> None:
        if ConnectedDevice.query.count():
            return
        devices = [
            ("192.168.1.12", "A4:5E:60:19:20:01", "workstation-01", "Dell"),
            ("192.168.1.18", "7C:8B:CA:19:20:02", "conference-room", "Apple"),
            ("192.168.1.24", "00:1A:11:19:20:03", "media-device", "Samsung"),
            ("192.168.1.31", "D8:3A:DD:19:20:04", "developer-laptop", "Lenovo"),
        ]
        for ip, mac, hostname, vendor in devices:
            db.session.add(ConnectedDevice(ip_address=ip, mac_address=mac, hostname=hostname, vendor=vendor))
        db.session.commit()

    def generate(self, count: int = 6) -> list[Traffic]:
        rows = []
        for _ in range(count):
            name, protocol, port, throughput_range, rate_range = random.choice(self.profiles)
            throughput = round(random.uniform(*throughput_range), 2)
            packet_rate = round(random.uniform(*rate_range), 1)
            classification = self.classifier.classify(protocol, port, packet_rate, throughput)
            row = Traffic(timestamp=datetime.now(timezone.utc), source_ip=f"192.168.1.{random.randint(10, 60)}", destination_ip=random.choice(["142.250.195.78", "13.107.42.14", "151.101.1.69"]), protocol=protocol, source_port=random.randint(1024, 65000), destination_port=port, packet_length=random.randint(300, 1500), packet_rate=packet_rate, throughput_mbps=throughput, upload_ratio=round(random.uniform(0.15, 0.75), 2), traffic_type=classification.traffic_type if classification.traffic_type else name, confidence=classification.confidence)
            db.session.add(row)
            rows.append(row)
        db.session.commit()
        return rows
