"""Database model package."""

from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


from app.models.network import (  # noqa: E402, F401
    BandwidthAllocation,
    ConnectedDevice,
    HistoricalLog,
    Prediction,
    Traffic,
    NetworkSnapshot,
    ForecastEvaluation,
)
