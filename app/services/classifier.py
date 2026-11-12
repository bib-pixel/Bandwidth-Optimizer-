"""Explainable rule-based traffic classification baseline (not a trained ML model)."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Classification:
    traffic_type: str
    confidence: float  # heuristic score only; not a calibrated probability
    method: str = "Rule-based classification"


class TrafficClassifier:
    """Simple port/traffic heuristics; scores are indicative and unvalidated."""
    def classify(self, protocol: str, destination_port: int, packet_rate: float, throughput: float) -> Classification:
        if destination_port in {3478, 8801, 19302} or (protocol == "UDP" and packet_rate > 85):
            return Classification("Video Conferencing", 0.91)
        if destination_port in {27015, 3074, 25565}:
            return Classification("Gaming", 0.93)
        if destination_port in {443, 1935} and throughput > 9:
            return Classification("Streaming", 0.88)
        if destination_port in {80, 443} and throughput < 5:
            return Classification("Web Browsing", 0.86)
        if throughput > 12:
            return Classification("File Download", 0.84)
        return Classification("Background Updates", 0.80)
