import time

from flask import Blueprint, Response, current_app, jsonify

from app.database import db
from app.metrics_store import (
    CACHE_HITS,
    CACHE_MISSES,
    DURATION_COUNT,
    DURATION_SUM,
    REQUEST_COUNTS,
    buckets_snapshot,
)
from app.models.url import ShortenedURL

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


@metrics_bp.route("/metrics/prometheus", methods=["GET"])
def metrics_prometheus():
    lines = []

    def _line(text):
        lines.append(text)

    # --- http_requests_total ---
    _line("# HELP http_requests_total Total HTTP requests by method, path, and status")
    _line("# TYPE http_requests_total counter")
    for (method, path, status), count in REQUEST_COUNTS.items():
        _line(f'http_requests_total{{method="{method}",path="{path}",status="{status}"}} {count}')

    # --- http_request_duration_seconds ---
    _line("# HELP http_request_duration_seconds HTTP request duration in seconds")
    _line("# TYPE http_request_duration_seconds histogram")
    for le, count in buckets_snapshot():
        le_str = "+Inf" if le == float("inf") else str(le)
        _line(f'http_request_duration_seconds_bucket{{le="{le_str}"}} {count}')
    _line(f"http_request_duration_seconds_sum {DURATION_SUM[0]:.6f}")
    _line(f"http_request_duration_seconds_count {DURATION_COUNT[0]}")

    # --- app_urls_total ---
    _line("# HELP app_urls_total Total number of shortened URLs")
    _line("# TYPE app_urls_total gauge")
    try:
        total_urls = ShortenedURL.select().count()
        active_urls = ShortenedURL.select().where(ShortenedURL.is_active == True).count()
    except Exception:
        total_urls = -1
        active_urls = -1
    _line(f"app_urls_total {total_urls}")

    # --- app_active_urls ---
    _line("# HELP app_active_urls Number of active shortened URLs")
    _line("# TYPE app_active_urls gauge")
    _line(f"app_active_urls {active_urls}")

    # --- app_cache_hits_total ---
    _line("# HELP app_cache_hits_total Total Redis cache hits")
    _line("# TYPE app_cache_hits_total counter")
    _line(f"app_cache_hits_total {CACHE_HITS[0]}")

    # --- app_cache_misses_total ---
    _line("# HELP app_cache_misses_total Total Redis cache misses")
    _line("# TYPE app_cache_misses_total counter")
    _line(f"app_cache_misses_total {CACHE_MISSES[0]}")

    return Response("\n".join(lines) + "\n", mimetype="text/plain; version=0.0.4")
