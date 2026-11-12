"""Application configuration classes."""

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


class Config:
    """Base configuration shared by all environments."""

    SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key-in-production")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'bandwidth_optimizer.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    SIMULATION_ENABLED = os.getenv("SIMULATION_ENABLED", "true").lower() == "true"
    TOTAL_BANDWIDTH_MBPS = float(os.getenv("TOTAL_BANDWIDTH_MBPS", "100"))
    MAX_TRAFFIC_RECORDS = int(os.getenv("MAX_TRAFFIC_RECORDS", "1000"))
    CAPTURE_MODE = os.getenv("CAPTURE_MODE", "simulation")
    CAPTURE_INTERFACE = os.getenv("CAPTURE_INTERFACE", "Wi-Fi")
    CAPTURE_BACKEND = os.getenv("CAPTURE_BACKEND", "scapy")
    # Windows Mobile Hotspot defaults; override these if your system differs.
    HOTSPOT_INTERFACE = os.getenv("HOTSPOT_INTERFACE", "Local Area Connection* 4")
    HOTSPOT_GATEWAY = os.getenv("HOTSPOT_GATEWAY", "192.168.137.1")
    QOS_ENFORCEMENT_ENABLED = os.getenv("QOS_ENFORCEMENT_ENABLED", "false").lower() == "true"
    QOS_INTERFACE = os.getenv("QOS_INTERFACE", "")


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
