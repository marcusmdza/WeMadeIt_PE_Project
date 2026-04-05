import json
import logging

from flask import Blueprint, jsonify, request
from peewee import DoesNotExist, InterfaceError, OperationalError
from playhouse.shortcuts import model_to_dict

from app.models.event import Event

events_bp = Blueprint("events", __name__)
logger = logging.getLogger(__name__)

_DB_ERRORS = (OperationalError, InterfaceError)


def _unavailable():
    return jsonify({"error": "Service temporarily unavailable"}), 503


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

        return jsonify([model_to_dict(e, backrefs=False) for e in query]), 200
    except _DB_ERRORS:
        logger.exception("Database error in GET /events")
        return _unavailable()


@events_bp.route("/events", methods=["POST"])
def create_event():
    data = request.get_json(silent=True) or {}

    event_type = data.get("event_type", "").strip()
    if not event_type:
        return jsonify({"error": "event_type is required"}), 400

    url_id = data.get("url_id")
    user_id = data.get("user_id")
    details = data.get("details")

    # Accept details as a dict and serialize to JSON string, or pass through as-is
    if isinstance(details, dict):
        details = json.dumps(details)

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

    return jsonify(model_to_dict(event, backrefs=False)), 201
