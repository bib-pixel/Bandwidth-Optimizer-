"""JSON and CSV API endpoints for the real-time dashboard."""

import csv
import io
from collections import Counter

from flask import Blueprint, Response, current_app, jsonify, request

from app.models import BandwidthAllocation, ConnectedDevice, HistoricalLog, Prediction, Traffic, db
from app.services.allocator import QosAllocator
from app.services.predictor import CongestionPredictor
from app.services.simulation import TrafficSimulator
from app.services.capture import monitor
from app.services.hotspot import HotspotDiscovery
from app.services.historical_predictor import HistoricalCongestionPredictor
from app.services.qos_policy import QosPolicyService

api_bp = Blueprint("api", __name__)


def serialize_traffic(row: Traffic) -> dict:
    return {"timestamp": row.timestamp.isoformat(), "source_ip": row.source_ip, "destination_ip": row.destination_ip, "protocol": row.protocol, "packet_length": row.packet_length, "packet_rate": row.packet_rate, "throughput_mbps": row.throughput_mbps, "traffic_type": row.traffic_type, "confidence": row.confidence}


def current_state() -> dict:
    capture_message = "Simulation data generated."
    if monitor.mode == "live":
        rows, capture_message = monitor.capture_window()
    elif current_app.config["SIMULATION_ENABLED"]:
        TrafficSimulator().generate()
        rows = Traffic.query.order_by(Traffic.timestamp.desc()).limit(30).all()
    else:
        rows = []
    throughput = round(sum(row.throughput_mbps for row in rows), 4)
    packet_rate = round(sum(row.packet_rate for row in rows), 2)
    upload = round(throughput * (sum(row.upload_ratio for row in rows) / len(rows)), 2) if rows else 0
    prediction = CongestionPredictor().predict(throughput, packet_rate, len(rows), upload / throughput if throughput else 0, current_app.config["TOTAL_BANDWIDTH_MBPS"])
    historical_forecast = HistoricalCongestionPredictor().observe_and_predict(throughput, packet_rate, len(rows), current_app.config["TOTAL_BANDWIDTH_MBPS"])
    hotspot = HotspotDiscovery()
    hotspot_interface = hotspot.find_interface()
    clients = hotspot.clients(hotspot_interface["IPAddress"]) if hotspot_interface else []
    observed_hosts = sorted({ip for row in rows for ip in (row.source_ip, row.destination_ip) if ip})
    selected_is_hotspot = bool(hotspot_interface and monitor.interface.casefold() == str(hotspot_interface.get("InterfaceAlias", "")).casefold())
    mismatch_warning = None
    if monitor.mode == "live" and hotspot_interface and not selected_is_hotspot:
        mismatch_warning = (f"Selected capture interface '{monitor.interface}' differs from detected hotspot adapter "
                           f"'{hotspot_interface['InterfaceAlias']}'. Hotspot-forwarded client traffic may not be visible.")
    elif monitor.mode == "live" and not hotspot_interface:
        mismatch_warning = "Windows hotspot adapter was not detected by its configured gateway IP. Capturing the selected interface may not include hotspot-client traffic."
    return {"rows": rows, "throughput": throughput, "upload": upload, "prediction": prediction, "historical_forecast": historical_forecast, "capture_message": capture_message, "hotspot": hotspot_interface, "clients": clients, "observed_hosts": observed_hosts, "interface_warning": mismatch_warning}


@api_bp.get("/dashboard")
def dashboard_data():
    state = current_state()
    rows, prediction = state["rows"], state["prediction"]
    observed = Counter()
    for row in rows:
        observed[row.traffic_type] += row.throughput_mbps
    allocations = QosAllocator().allocate(current_app.config["TOTAL_BANDWIDTH_MBPS"], observed)
    active_devices = len(state["clients"]) if monitor.mode == "live" else ConnectedDevice.query.filter_by(status="online").count()
    device_usage = Counter()
    for row in rows:
        device_usage[row.source_ip] += row.throughput_mbps
        device_usage[row.destination_ip] += row.throughput_mbps
    clients = [{**client, "observed_mbps": round(device_usage[client["ip_address"]], 4)} for client in state["clients"]]
    qos = QosPolicyService().recommend(state["historical_forecast"], current_app.config["TOTAL_BANDWIDTH_MBPS"])
    return jsonify({"summary": {"configured_capacity_mbps": current_app.config["TOTAL_BANDWIDTH_MBPS"], "current_usage": state["throughput"], "upload_speed": state["upload"], "download_speed": round(max(0, state["throughput"] - state["upload"]), 4), "active_devices": active_devices, "device_count_label": "Hotspot ARP entries" if monitor.mode == "live" else "Simulated devices", "active_flows": len(rows), "congestion_level": prediction.level, "heuristic_confidence": prediction.confidence, "latency_ms": prediction.latency_ms, "usage_percent": prediction.usage_percent}, "forecast": state["historical_forecast"], "qos_policy": qos, "capture": {"mode": monitor.mode, "interface": monitor.interface, "message": state["capture_message"], "interface_warning": state["interface_warning"]}, "hotspot": {"interface": state["hotspot"], "clients": clients, "discovery_note": "Hotspot clients are inferred from the Windows ARP cache; entries can be missing or stale."}, "observed_hosts": state["observed_hosts"], "traffic": [serialize_traffic(row) for row in rows[:15]], "distribution": dict(observed), "allocations": allocations, "throughput_history": [round(row.throughput_mbps, 4) for row in reversed(rows[:12])]}), 200


@api_bp.get("/interfaces")
def interfaces():
    names = monitor.interfaces()
    hotspot = HotspotDiscovery().find_interface()
    if hotspot and hotspot["InterfaceAlias"] not in names:
        names.append(hotspot["InterfaceAlias"])
    warning = None
    if hotspot is None:
        warning = "Could not detect the hotspot adapter by gateway IP. Check HOTSPOT_GATEWAY in .env and enable Mobile Hotspot."
    return jsonify({"interfaces": sorted(set(names), key=str.casefold), "selected": monitor.interface, "mode": monitor.mode, "hotspot": hotspot, "warning": warning})


@api_bp.post("/capture/configure")
def configure_capture():
    data = request.get_json(silent=True) or {}
    status = monitor.configure(str(data.get("mode", "simulation")), str(data.get("interface", "Wi-Fi")))
    hotspot = HotspotDiscovery().find_interface()
    warning = None
    if status.mode == "live" and hotspot and status.interface.casefold() != str(hotspot.get("InterfaceAlias", "")).casefold():
        warning = f"Selected interface '{status.interface}' differs from hotspot adapter '{hotspot['InterfaceAlias']}'. Hotspot-client traffic may not be visible."
    elif status.mode == "live" and not hotspot:
        warning = "Hotspot adapter could not be detected. Live capture will monitor only the selected interface."
    return jsonify({"mode": status.mode, "interface": status.interface, "message": status.message, "interface_warning": warning})


@api_bp.get("/qos/status")
def qos_status():
    service = QosPolicyService()
    return jsonify({"enforcement_enabled": current_app.config.get("QOS_ENFORCEMENT_ENABLED", False),
                    "interface": current_app.config.get("QOS_INTERFACE", ""),
                    "backend": service.linux_tc_status(),
                    "message": "Enforcement is opt-in and must be verified on a controlled network."})


@api_bp.post("/qos/apply")
def apply_qos():
    # This endpoint never applies a policy unless the operator explicitly enables it in .env.
    enabled = bool(current_app.config.get("QOS_ENFORCEMENT_ENABLED", False))
    interface = str(current_app.config.get("QOS_INTERFACE", ""))
    if not enabled or not interface:
        return jsonify({"applied": False, "status": "disabled", "message": "QoS enforcement is disabled. Set QOS_ENFORCEMENT_ENABLED=true and QOS_INTERFACE explicitly after reviewing the risks."}), 409
    result = QosPolicyService().apply_linux_htb(interface, current_app.config["TOTAL_BANDWIDTH_MBPS"], enabled=enabled)
    return jsonify(result), (200 if result.get("applied") else 400)


@api_bp.get("/traffic")
def traffic_data():
    return jsonify([serialize_traffic(row) for row in Traffic.query.order_by(Traffic.timestamp.desc()).limit(100).all()])


@api_bp.get("/devices")
def device_data():
    rows = ConnectedDevice.query.order_by(ConnectedDevice.hostname).all()
    return jsonify([{"ip_address": row.ip_address, "mac_address": row.mac_address, "hostname": row.hostname, "vendor": row.vendor, "status": row.status, "last_seen": row.last_seen.isoformat()} for row in rows])


@api_bp.get("/hotspot/devices")
def hotspot_devices():
    discovery = HotspotDiscovery()
    hotspot = discovery.find_interface()
    clients = discovery.clients(hotspot["IPAddress"]) if hotspot else []
    return jsonify({"hotspot": hotspot, "clients": clients, "count": len(clients)})


@api_bp.get("/export/traffic.csv")
def export_traffic():
    output = io.StringIO(); writer = csv.writer(output)
    writer.writerow(["Timestamp", "Source IP", "Destination IP", "Protocol", "Traffic Type", "Throughput Mbps", "Confidence"])
    for row in Traffic.query.order_by(Traffic.timestamp.desc()).all():
        writer.writerow([row.timestamp.isoformat(), row.source_ip, row.destination_ip, row.protocol, row.traffic_type, row.throughput_mbps, row.confidence])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=traffic-report.csv"})
