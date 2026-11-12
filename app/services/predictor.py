"""Heuristic congestion estimate; no trained model is loaded by this service."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class CongestionPrediction:
    level: str
    confidence: float  # heuristic score, not a model probability
    latency_ms: float
    usage_percent: float
    method: str = "Heuristic estimate"


class CongestionPredictor:
    def predict(self, throughput: float, packet_rate: float, flow_count: int, upload_ratio: float, total_bandwidth: float) -> CongestionPrediction:
        usage = min(100.0, (throughput / max(total_bandwidth, 1.0)) * 100)
        pressure = usage * 0.72 + min(packet_rate / 8, 15) + min(flow_count * 1.5, 10) + upload_ratio * 8
        if pressure >= 78:
            level = "High"
        elif pressure >= 48:
            level = "Medium"
        else:
            level = "Low"
        # Report a transparent heuristic score, not an implied calibrated probability.
        score = max(0.0, min(1.0, pressure / 100.0))
        latency = round(8 + usage * 0.42 + packet_rate * 0.05, 1)
        return CongestionPrediction(level, round(score, 2), latency, round(usage, 1))
