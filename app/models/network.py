"""SQLAlchemy entities for traffic monitoring and AI decisions."""

from datetime import datetime, timezone

from app.models import db


def utcnow():
    return datetime.now(timezone.utc)


class Traffic(db.Model):
    __tablename__ = "traffic"
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    source_ip = db.Column(db.String(45), nullable=False)
    destination_ip = db.Column(db.String(45), nullable=False)
    protocol = db.Column(db.String(12), nullable=False)
    source_port = db.Column(db.Integer, nullable=True)
    destination_port = db.Column(db.Integer, nullable=True)
    packet_length = db.Column(db.Integer, nullable=False)
    packet_rate = db.Column(db.Float, nullable=False)
    throughput_mbps = db.Column(db.Float, nullable=False)
    upload_ratio = db.Column(db.Float, nullable=False)
    traffic_type = db.Column(db.String(40), nullable=False)
    confidence = db.Column(db.Float, nullable=False)


class Prediction(db.Model):
    __tablename__ = "predictions"
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    congestion_level = db.Column(db.String(12), nullable=False)
    confidence = db.Column(db.Float, nullable=False)
    latency_ms = db.Column(db.Float, nullable=False)
    bandwidth_usage = db.Column(db.Float, nullable=False)


class BandwidthAllocation(db.Model):
    __tablename__ = "bandwidth_allocations"
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    traffic_type = db.Column(db.String(40), nullable=False)
    percentage = db.Column(db.Float, nullable=False)
    allocated_mbps = db.Column(db.Float, nullable=False)
    priority = db.Column(db.String(12), nullable=False)
    reason = db.Column(db.String(255), nullable=False)


class HistoricalLog(db.Model):
    __tablename__ = "historical_logs"
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    event_type = db.Column(db.String(50), nullable=False)
    message = db.Column(db.String(500), nullable=False)


class ConnectedDevice(db.Model):
    __tablename__ = "connected_devices"
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), nullable=False, unique=True)
    mac_address = db.Column(db.String(17), nullable=False)
    hostname = db.Column(db.String(100), nullable=False)
    vendor = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="online")
    last_seen = db.Column(db.DateTime, nullable=False, default=utcnow)


class NetworkSnapshot(db.Model):
    """Timestamped aggregate measurements used for historical forecasting."""
    __tablename__ = "network_snapshots"
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    throughput_mbps = db.Column(db.Float, nullable=False)
    packet_rate = db.Column(db.Float, nullable=False)
    flow_count = db.Column(db.Integer, nullable=False)
    usage_percent = db.Column(db.Float, nullable=False)


class ForecastEvaluation(db.Model):
    """Out-of-sample forecast records paired with actual later observations."""
    __tablename__ = "forecast_evaluations"
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    target_at = db.Column(db.DateTime, nullable=False, index=True)
    predicted_throughput_mbps = db.Column(db.Float, nullable=False)
    actual_throughput_mbps = db.Column(db.Float, nullable=True)
    absolute_error_mbps = db.Column(db.Float, nullable=True)
    method = db.Column(db.String(80), nullable=False)
    evaluated_at = db.Column(db.DateTime, nullable=True)
