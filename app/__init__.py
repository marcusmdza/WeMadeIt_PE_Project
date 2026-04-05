import logging
import time

from dotenv import load_dotenv
from flask import Flask, g, jsonify, request

from app.alerts import record_error_and_maybe_alert, register_cli
from app.database import init_db
from app.logging_config import configure_logging
from app.metrics_store import record_request
from app.routes import register_routes

logger = logging.getLogger(__name__)


def create_app():
    load_dotenv()
    configure_logging()

    app = Flask(__name__)

    app.config["APP_START_TIME"] = time.time()
    app.config["TOTAL_REQUESTS"] = 0
    app.config["TOTAL_ERRORS"] = 0

    init_db(app)

    from app import models  # noqa: F401 - registers models with Peewee
    from app.database import db
    from app.models.event import Event
    from app.models.url import ShortenedURL
    from app.models.user import User

    with app.app_context():
        db.connect(reuse_if_open=True)
        db.create_tables([User, ShortenedURL, Event], safe=True)

    register_routes(app)

    @app.before_request
    def _record_start_time():
        g.start_time = time.time()

    register_cli(app)

    @app.after_request
    def _log_request(response):
        app.config["TOTAL_REQUESTS"] += 1
        if response.status_code >= 400:
            app.config["TOTAL_ERRORS"] += 1
            record_error_and_maybe_alert()

        duration_s = time.time() - g.start_time
        # Normalise path to URL rule to avoid high-cardinality labels like /urls/123
        path = str(request.url_rule) if request.url_rule else request.path
        record_request(request.method, path, response.status_code, duration_s)

        logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
                "duration_ms": round(duration_s * 1000, 2),
            },
        )
        return response

    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({"error": "Bad request"}), 400

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"error": "Method not allowed"}), 405

    @app.errorhandler(410)
    def gone(e):
        return jsonify({"error": "Gone"}), 410

    @app.errorhandler(500)
    def internal_error(e):
        app.logger.error("Unhandled exception", exc_info=e)
        return jsonify({"error": "Internal server error"}), 500

    @app.route("/health")
    def health():
        return jsonify(status="ok")

    return app
