"""Database query helpers used by controllers and export endpoints."""

from app.models import Traffic


def recent_traffic(limit: int = 25) -> list[Traffic]:
    return Traffic.query.order_by(Traffic.timestamp.desc()).limit(limit).all()
