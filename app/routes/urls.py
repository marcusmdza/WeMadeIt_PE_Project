import datetime
import json
import logging
import random
import string

from flask import Blueprint, jsonify, redirect, request
from peewee import DatabaseError, DoesNotExist, IntegrityError
from playhouse.shortcuts import model_to_dict

from app.models.event import Event
from app.models.url import ShortenedURL

urls_bp = Blueprint("urls", __name__)
logger = logging.getLogger(__name__)


def _unavailable():
    return jsonify({"error": "Service temporarily unavailable"}), 503


def _generate_short_code(length=6):
    chars = string.ascii_letters + string.digits
    return "".join(random.choices(chars, k=length))


@urls_bp.route("/shorten", methods=["POST"])
def shorten():
    data = request.get_json(silent=True) or {}
    original_url = data.get("url", "").strip()

    if not original_url:
        return jsonify({"error": "URL is required"}), 400
    if not original_url.startswith(("http://", "https://")):
        return jsonify({"error": "URL must start with http:// or https://"}), 400

    title = data.get("title")
    user_id = data.get("user_id")

    try:
        url_record = None
        for _ in range(3):
            short_code = _generate_short_code()
            try:
                url_record = ShortenedURL.create(
                    original_url=original_url,
                    short_code=short_code,
                    title=title,
                    user=user_id,
                )
                break
            except IntegrityError:
                continue

        if url_record is None:
            return jsonify({"error": "Failed to generate a unique short code, please retry"}), 500

        Event.create(
            url=url_record,
            user=user_id,
            event_type="created",
            details=json.dumps({"short_code": short_code, "original_url": original_url}),
        )
    except DatabaseError:
        logger.exception("Database error in POST /shorten")
        return _unavailable()

    return jsonify(model_to_dict(url_record, backrefs=False)), 201


@urls_bp.route("/<short_code>", methods=["GET"])
def redirect_url(short_code):
    try:
        url_record = ShortenedURL.get(ShortenedURL.short_code == short_code)
    except DoesNotExist:
        return jsonify({"error": "URL not found"}), 404
    except DatabaseError:
        logger.exception("Database error in GET /<short_code>")
        return _unavailable()

    if not url_record.is_active:
        return jsonify({"error": "This URL is no longer active"}), 410

    try:
        ShortenedURL.update(click_count=ShortenedURL.click_count + 1).where(
            ShortenedURL.short_code == short_code
        ).execute()
    except DatabaseError:
        # Non-fatal: log and continue so the redirect still works.
        logger.warning("Failed to increment click_count for %s", short_code)

    return redirect(url_record.original_url, code=302)


@urls_bp.route("/urls", methods=["GET"])
def list_urls():
    try:
        query = ShortenedURL.select()
        active_param = request.args.get("active")
        if active_param == "true":
            query = query.where(ShortenedURL.is_active == True)
        elif active_param == "false":
            query = query.where(ShortenedURL.is_active == False)
        return jsonify([model_to_dict(u, backrefs=False) for u in query]), 200
    except DatabaseError:
        logger.exception("Database error in GET /urls")
        return _unavailable()


@urls_bp.route("/urls/<int:url_id>", methods=["GET"])
def get_url(url_id):
    try:
        url_record = ShortenedURL.get_by_id(url_id)
    except DoesNotExist:
        return jsonify({"error": "URL not found"}), 404
    except DatabaseError:
        logger.exception("Database error in GET /urls/%s", url_id)
        return _unavailable()
    return jsonify(model_to_dict(url_record, backrefs=False)), 200


@urls_bp.route("/urls/<int:url_id>", methods=["PUT"])
def update_url(url_id):
    try:
        url_record = ShortenedURL.get_by_id(url_id)
    except DoesNotExist:
        return jsonify({"error": "URL not found"}), 404
    except DatabaseError:
        logger.exception("Database error in PUT /urls/%s", url_id)
        return _unavailable()

    data = request.get_json(silent=True) or {}
    try:
        if "title" in data:
            url_record.title = data["title"]
        if "original_url" in data:
            url_record.original_url = data["original_url"]
        if "is_active" in data:
            url_record.is_active = data["is_active"]
        url_record.updated_at = datetime.datetime.now()
        url_record.save()

        Event.create(
            url=url_record,
            event_type="updated",
            details=json.dumps(data),
        )
    except DatabaseError:
        logger.exception("Database error saving PUT /urls/%s", url_id)
        return _unavailable()

    return jsonify(model_to_dict(url_record, backrefs=False)), 200


@urls_bp.route("/urls/<int:url_id>", methods=["DELETE"])
def delete_url(url_id):
    try:
        url_record = ShortenedURL.get_by_id(url_id)
    except DoesNotExist:
        return jsonify({"error": "URL not found"}), 404
    except DatabaseError:
        logger.exception("Database error in DELETE /urls/%s", url_id)
        return _unavailable()

    try:
        url_record.is_active = False
        url_record.save()

        Event.create(
            url=url_record,
            event_type="deleted",
        )
    except DatabaseError:
        logger.exception("Database error saving DELETE /urls/%s", url_id)
        return _unavailable()

    return jsonify({"message": "URL deleted"}), 200
