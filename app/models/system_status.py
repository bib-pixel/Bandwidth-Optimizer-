"""Example model used to validate database connectivity."""

from datetime import datetime, timezone

from app.models import db


class SystemStatus(db.Model):
    """Stores application status events for future monitoring features."""

    __tablename__ = "system_statuses"

    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(50), nullable=False, default="healthy")
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
