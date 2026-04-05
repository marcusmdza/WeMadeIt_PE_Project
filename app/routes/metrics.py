import time

from flask import Blueprint, current_app, jsonify

from app.database import db

metrics_bp = Blueprint("metrics", __name__)


@metrics_bp.route("/metrics", methods=["GET"])
def metrics():
    uptime_seconds = round(time.time() - current_app.config["APP_START_TIME"], 2)

    try:
        db.execute_sql("SELECT 1")
        database_status = "connected"
    except Exception:
        database_status = "disconnected"

    return jsonify(
        {
            "uptime_seconds": uptime_seconds,
            "total_requests": current_app.config["TOTAL_REQUESTS"],
            "total_errors": current_app.config["TOTAL_ERRORS"],
            "database_status": database_status,
        }
    ), 200
