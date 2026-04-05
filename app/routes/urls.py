import datetime
import json
import logging
import random
import string

from flask import Blueprint, jsonify, redirect, request
from peewee import DoesNotExist, IntegrityError, InterfaceError, OperationalError
from playhouse.shortcuts import model_to_dict

from app.cache import cache_url, get_cached_url, invalidate_url
from app.models.event import Event
from app.models.url import ShortenedURL

urls_bp = Blueprint("urls", __name__)
logger = logging.getLogger(__name__)

_DB_ERRORS = (OperationalError, InterfaceError)


def _unavailable():
    return jsonify({"error": "Service temporarily unavailable"}), 503


def _generate_short_code(length=6):
    chars = string.ascii_letters + string.digits
    return "".join(random.choices(chars, k=length))


def _create_url(original_url, title=None, user_id=None):
    """Shared logic for POST /shorten and POST /urls. Returns (url_record, error_response)."""
    if not original_url:
        return None, (jsonify({"error": "URL is required"}), 400)
    if not original_url.startswith(("http://", "https://")):
        return None, (jsonify({"error": "URL must start with http:// or https://"}), 400)

    url_record = None
    try:
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
            return None, (jsonify({"error": "Failed to generate a unique short code, please retry"}), 500)

        Event.create(
            url=url_record,
            user=user_id,
            event_type="created",
            details=json.dumps({"short_code": url_record.short_code, "original_url": original_url}),
        )
    except _DB_ERRORS:
        logger.exception("Database error creating URL")
        return None, _unavailable()

    return url_record, None


@urls_bp.route("/shorten", methods=["POST"])
def shorten():
    data = request.get_json(silent=True) or {}
    original_url = data.get("url", "").strip()
    url_record, err = _create_url(original_url, data.get("title"), data.get("user_id"))
    if err:
        return err
    return jsonify(model_to_dict(url_record, backrefs=False)), 201


@urls_bp.route("/urls", methods=["POST"])
def create_url():
    data = request.get_json(silent=True) or {}
    original_url = data.get("original_url", "").strip()
    url_record, err = _create_url(original_url, data.get("title"), data.get("user_id"))
    if err:
        return err
    return jsonify(model_to_dict(url_record, backrefs=False)), 201


@urls_bp.route("/<short_code>", methods=["GET"])
def redirect_url(short_code):
    cache_hit = False
    cached = get_cached_url(short_code)

    if cached:
        original_url = cached["original_url"]
        is_active = cached["is_active"]
        cache_hit = True
    else:
        try:
            url_record = ShortenedURL.get(ShortenedURL.short_code == short_code)
        except DoesNotExist:
            return jsonify({"error": "URL not found"}), 404
        except _DB_ERRORS:
            logger.exception("Database error in GET /<short_code>")
            return _unavailable()

        original_url = url_record.original_url
        is_active = url_record.is_active
        cache_url(short_code, {"original_url": original_url, "is_active": is_active})

    if not is_active:
        return jsonify({"error": "This URL is no longer active"}), 410

    try:
        ShortenedURL.update(click_count=ShortenedURL.click_count + 1).where(
            ShortenedURL.short_code == short_code
        ).execute()
    except _DB_ERRORS:
        logger.warning("Failed to increment click_count for %s", short_code)

    response = redirect(original_url, code=302)
    response.headers["X-Cache"] = "HIT" if cache_hit else "MISS"
    return response


@urls_bp.route("/urls", methods=["GET"])
def list_urls():
    try:
        query = ShortenedURL.select()

        active_param = request.args.get("active") or request.args.get("is_active")
        if active_param == "true":
            query = query.where(ShortenedURL.is_active == True)
        elif active_param == "false":
            query = query.where(ShortenedURL.is_active == False)

        user_id = request.args.get("user_id", type=int)
        if user_id is not None:
            query = query.where(ShortenedURL.user == user_id)

        results = []
        for u in query:
            d = model_to_dict(u, backrefs=False)
            d["user_id"] = u.user_id
            results.append(d)
        return jsonify(results), 200
    except _DB_ERRORS:
        logger.exception("Database error in GET /urls")
        return _unavailable()


@urls_bp.route("/urls/<int:url_id>", methods=["GET"])
def get_url(url_id):
    try:
        url_record = ShortenedURL.get_by_id(url_id)
    except DoesNotExist:
        return jsonify({"error": "URL not found"}), 404
    except _DB_ERRORS:
        logger.exception("Database error in GET /urls/%s", url_id)
        return _unavailable()
    d = model_to_dict(url_record, backrefs=False)
    d["user_id"] = url_record.user_id
    return jsonify(d), 200


@urls_bp.route("/urls/<int:url_id>", methods=["PUT"])
def update_url(url_id):
    try:
        url_record = ShortenedURL.get_by_id(url_id)
    except DoesNotExist:
        return jsonify({"error": "URL not found"}), 404
    except _DB_ERRORS:
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
    except _DB_ERRORS:
        logger.exception("Database error saving PUT /urls/%s", url_id)
        return _unavailable()

    invalidate_url(url_record.short_code)
    return jsonify(model_to_dict(url_record, backrefs=False)), 200


@urls_bp.route("/urls/<int:url_id>", methods=["DELETE"])
def delete_url(url_id):
    try:
        url_record = ShortenedURL.get_by_id(url_id)
    except DoesNotExist:
        return jsonify({"error": "URL not found"}), 404
    except _DB_ERRORS:
        logger.exception("Database error in DELETE /urls/%s", url_id)
        return _unavailable()

    try:
        url_record.is_active = False
        url_record.save()
        Event.create(url=url_record, event_type="deleted")
    except _DB_ERRORS:
        logger.exception("Database error saving DELETE /urls/%s", url_id)
        return _unavailable()

    invalidate_url(url_record.short_code)
    return jsonify({"message": "URL deleted"}), 200
