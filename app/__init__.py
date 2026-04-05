import logging
import time

from dotenv import load_dotenv
from flask import Flask, g, jsonify, request

from app.database import init_db
from app.logging_config import configure_logging
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

    register_routes(app)

    @app.before_request
    def _record_start_time():
        g.start_time = time.time()

    @app.after_request
    def _log_request(response):
        app.config["TOTAL_REQUESTS"] += 1
        if response.status_code >= 400:
            app.config["TOTAL_ERRORS"] += 1

        duration_ms = round((time.time() - g.start_time) * 1000, 2)
        logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
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
