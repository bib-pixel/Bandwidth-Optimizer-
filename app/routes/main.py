"""Routes for the initial application interface."""

from flask import Blueprint, jsonify, render_template


main_bp = Blueprint("main", __name__)


@main_bp.get("/")
def index():
    """Render the initial system dashboard placeholder."""
    return render_template("index.html", title="AI-Based Predictive Bandwidth Optimization")


@main_bp.get("/dashboard")
def dashboard():
    return render_template("dashboard.html", title="Network Intelligence Dashboard")


@main_bp.get("/traffic")
def traffic():
    return render_template("traffic.html", title="Live Traffic")


@main_bp.get("/allocation")
def allocation():
    return render_template("allocation.html", title="Adaptive QoS Allocation")


@main_bp.get("/prediction")
@main_bp.get("/statistics")
@main_bp.get("/devices")
def dashboard_alias():
    return dashboard()


@main_bp.get("/health")
def health_check():
    """Provide a lightweight service health endpoint."""
    return jsonify({"status": "healthy"}), 200
