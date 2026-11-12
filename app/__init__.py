"""Flask application factory and extension setup."""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from flask import Flask

from config import config_by_name
from app.models import db


def configure_logging(app: Flask) -> None:
    """Configure file and console logging once for the application."""
    logs_directory = Path(app.root_path).parent / "logs"
    logs_directory.mkdir(exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )
    file_handler = RotatingFileHandler(
        logs_directory / "application.log", maxBytes=1_000_000, backupCount=5
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(getattr(logging, app.config["LOG_LEVEL"].upper(), logging.INFO))

    app.logger.handlers.clear()
    app.logger.addHandler(file_handler)
    app.logger.setLevel(file_handler.level)
    app.logger.propagate = False


def create_app(config_name: Optional[str] = None) -> Flask:
    """Create and configure the Flask application."""
    selected_config = config_name or os.getenv("FLASK_ENV", "default")
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_by_name.get(selected_config, config_by_name["default"]))

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    configure_logging(app)

    db.init_app(app)

    from app.routes.main import main_bp
    from app.routes.api import api_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    with app.app_context():
        db.create_all()
        from app.services.simulation import TrafficSimulator
        TrafficSimulator().seed_devices()

    app.logger.info("Application initialized in %s mode", selected_config)
    return app
