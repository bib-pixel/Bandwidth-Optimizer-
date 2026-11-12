"""Proactive QoS policy planner with explicit, opt-in Linux tc enforcement.

Windows/Npcap capture does not itself provide a traffic-shaping API. On Windows
this service returns a recommendation only. Linux tc enforcement is disabled by
default and requires an explicit config flag, interface, and elevated privileges.
"""
from __future__ import annotations
import os
import platform
import shlex
import subprocess
from typing import Any

PRIORITIES = {
    "Video Conferencing": 1,
    "Gaming": 2,
    "Web Browsing": 3,
    "Streaming": 4,
    "File Download": 5,
    "Background Updates": 6,
}

class QosPolicyService:
    def recommend(self, forecast: dict[str, Any], capacity_mbps: float) -> dict[str, Any]:
        predicted = forecast.get("predicted_throughput_mbps")
        usage = forecast.get("predicted_usage_percent")
        level = forecast.get("predicted_level", "Unknown")
        ready = bool(forecast.get("ready") and predicted is not None)
        # Conservative policy suggestions; these are not enforced reservations.
        reserve = round(max(0.0, capacity_mbps) * 0.15, 2)
        actions = []
        if not ready:
            actions.append("Continue collecting measurements; do not automatically change network policy.")
        elif level == "High" or (usage is not None and usage >= 85):
            actions.extend([
                f"Prepare a high-priority class for real-time traffic with up to {reserve:.2f} Mbps of the configured capacity as a planning target.",
                "Defer or rate-limit bulk transfers only if an administrator-approved shaper is configured.",
                "Recheck measured utilization after the predicted peak and record whether the forecast was correct.",
            ])
        elif level == "Medium" or (usage is not None and usage >= 65):
            actions.extend([
                "Pre-stage the QoS policy and monitor the next forecast interval.",
                "Prefer interactive traffic over bulk transfers if the network scheduler supports those classes.",
            ])
        else:
            actions.extend(["No proactive restriction recommended from this forecast.", "Continue monitoring for a rising trend."])
        backend = "linux_tc" if platform.system() == "Linux" else "recommendation_only"
        return {
            "status": "recommendation_only",
            "enforcement_enabled": False,
            "backend_available": backend == "linux_tc",
            "predicted_level": level,
            "predicted_usage_percent": usage,
            "configured_capacity_mbps": round(float(capacity_mbps), 3),
            "planning_reserve_mbps": reserve,
            "actions": actions,
            "message": "A policy recommendation is not an enforced reservation. Enforcement is disabled by default.",
        }

    def linux_tc_status(self) -> dict[str, Any]:
        if platform.system() != "Linux":
            return {"available": False, "reason": "The current host is not Linux. Windows capture via Npcap does not expose Linux tc shaping."}
        try:
            result = subprocess.run(["tc", "-V"], capture_output=True, text=True, timeout=3, check=False)
            if result.returncode == 0:
                return {"available": True, "version": (result.stdout or result.stderr).strip()}
            return {"available": False, "reason": result.stderr.strip() or "tc is unavailable."}
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"available": False, "reason": str(exc)}

    def apply_linux_htb(self, interface: str, capacity_mbps: float, enabled: bool = False) -> dict[str, Any]:
        """Apply only a root HTB cap, not app-specific classification.

        This deliberately refuses unless explicitly enabled and on Linux. It is
        a basic interface cap, not a complete per-application PQ/WFQ scheduler.
        """
        if not enabled:
            return {"applied": False, "status": "disabled", "message": "Set QOS_ENFORCEMENT_ENABLED=true and explicitly configure an interface to enable shaping."}
        if platform.system() != "Linux":
            return {"applied": False, "status": "unsupported", "message": "Automatic tc shaping is supported only on Linux in this implementation."}
        if not interface or interface.startswith("-") or any(c.isspace() for c in interface):
            return {"applied": False, "status": "invalid_interface", "message": "Provide a single valid network interface name."}
        if capacity_mbps <= 0:
            return {"applied": False, "status": "invalid_capacity", "message": "Capacity must be positive."}
        # Explicit commands; no shell interpolation. Replaces root qdisc, so opt-in only.
        commands = [
            ["tc", "qdisc", "replace", "dev", interface, "root", "handle", "1:", "htb", "default", "10"],
            ["tc", "class", "replace", "dev", interface, "parent", "1:", "classid", "1:10", "htb", "rate", f"{float(capacity_mbps):g}mbit", "ceil", f"{float(capacity_mbps):g}mbit"],
        ]
        completed = []
        try:
            for command in commands:
                result = subprocess.run(command, capture_output=True, text=True, timeout=8, check=False)
                completed.append({"command": shlex.join(command), "returncode": result.returncode})
                if result.returncode:
                    return {"applied": False, "status": "failed", "commands": completed, "message": result.stderr.strip() or "tc command failed."}
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"applied": False, "status": "failed", "commands": completed, "message": str(exc)}
        return {"applied": True, "status": "applied", "commands": completed,
                "message": "Applied an interface-wide HTB cap. This does not implement per-application PQ/WFQ; verify with tc qdisc/class show and a controlled traffic test."}
