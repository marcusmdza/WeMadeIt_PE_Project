import json
import logging

from flask import Blueprint, jsonify, request
from peewee import InterfaceError, OperationalError
from playhouse.shortcuts import model_to_dict

from app.models.event import Event
from app.models.url import ShortenedURL
from app.models.user import User

events_bp = Blueprint("events", __name__)
logger = logging.getLogger(__name__)

_DB_ERRORS = (OperationalError, InterfaceError)


def _unavailable():
    return jsonify({"error": "Service temporarily unavailable"}), 503


def _require_json():
    if not request.content_type or "application/json" not in request.content_type:
        return jsonify({"error": "Content-Type must be application/json"}), 415
    if request.get_json(silent=True) is None:
        return jsonify({"error": "Invalid JSON"}), 400
    return None


@events_bp.route("/events", methods=["GET"])
def list_events():
    try:
        query = Event.select().order_by(Event.id)

        url_id = request.args.get("url_id", type=int)
        if url_id is not None:
            query = query.where(Event.url == url_id)

        user_id = request.args.get("user_id", type=int)
        if user_id is not None:
            query = query.where(Event.user == user_id)

        event_type = request.args.get("event_type")
        if event_type:
            query = query.where(Event.event_type == event_type)

        results = []
        for e in query:
            d = model_to_dict(e, backrefs=False)
            d["url_id"] = e.url_id
            d["user_id"] = e.user_id
            results.append(d)
        return jsonify(results), 200
    except _DB_ERRORS:
        logger.exception("Database error in GET /events")
        return _unavailable()


@events_bp.route("/events", methods=["POST"])
def create_event():
    err = _require_json()
    if err:
        return err
    data = request.get_json()

    event_type = data.get("event_type", "").strip()
    if not event_type:
        return jsonify({"error": "event_type is required"}), 400

    url_id = data.get("url_id")
    user_id = data.get("user_id")
    details = data.get("details")

    # Hint 5: details must be a dict if provided
    if details is not None and not isinstance(details, dict):
        return jsonify({"error": "Details must be a JSON object"}), 400
    if isinstance(details, dict):
        details = json.dumps(details)

    # Hint 3: validate FK existence
    if url_id is not None:
        if ShortenedURL.get_or_none(ShortenedURL.id == url_id) is None:
            return jsonify({"error": "URL not found"}), 404
    if user_id is not None:
        if User.get_or_none(User.id == user_id) is None:
            return jsonify({"error": "User not found"}), 404

    try:
        event = Event.create(
            url=url_id,
            user=user_id,
            event_type=event_type,
            details=details,
        )
    except _DB_ERRORS:
        logger.exception("Database error in POST /events")
        return _unavailable()

    d = model_to_dict(event, backrefs=False)
    d["url_id"] = event.url_id
    d["user_id"] = event.user_id
    return jsonify(d), 201
