"""Software-only adaptive QoS allocation engine."""

from __future__ import annotations


class QosAllocator:
    categories = ["Video Conferencing", "Gaming", "Streaming", "Web Browsing", "File Download", "Background Updates"]

    def allocate(self, total_mbps: float, observed_mbps: dict[str, float]) -> list[dict]:
        """Return observed traffic shares, rather than preset QoS reservations.

        This application monitors traffic only; it cannot enforce a router QoS
        policy.  The percentages therefore report measured usage during the
        current capture window and never reserve bandwidth for an idle class.
        """
        total_observed = sum(max(0, value) for value in observed_mbps.values())
        result = []
        for category, usage in sorted(observed_mbps.items(), key=lambda item: item[1], reverse=True):
            if usage <= 0:
                continue
            percentage = round(usage / total_observed * 100, 1) if total_observed else 0
            result.append({
                "traffic_type": category,
                "percentage": percentage,
                "allocated_mbps": round(usage, 3),
                "priority": "Observed",
                "reason": "Measured in the current capture window; not a reserved bandwidth policy.",
            })
        return result
