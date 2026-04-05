import datetime
import json
import logging
import random
import string

from flask import Blueprint, jsonify, redirect, request
from peewee import DoesNotExist, ForeignKeyField, IntegrityError, InterfaceError, OperationalError
from playhouse.shortcuts import model_to_dict

from app.cache import cache_url, get_cached_url, invalidate_url
from app.models.event import Event
from app.models.url import ShortenedURL
from app.models.user import User

urls_bp = Blueprint("urls", __name__)
logger = logging.getLogger(__name__)

_DB_ERRORS = (OperationalError, InterfaceError)


def _unavailable():
    return jsonify({"error": "Service temporarily unavailable"}), 503


def _require_json():
    """Return an error response tuple if request is not valid JSON, else None."""
    if not request.content_type or "application/json" not in request.content_type:
        return jsonify({"error": "Content-Type must be application/json"}), 415
    if request.get_json(silent=True) is None:
        return jsonify({"error": "Invalid JSON"}), 400
    return None


def _generate_short_code(length=6):
    chars = string.ascii_letters + string.digits
    return "".join(random.choices(chars, k=length))


def _url_dict(url_record):
    d = model_to_dict(url_record, backrefs=False, exclude=[ShortenedURL.user])
    d["user_id"] = url_record.user_id
    return d


def _create_url(original_url, title=None, user_id=None):
    """Returns (url_record, http_status, error_response). status is 200 for existing, 201 for new."""
    if not original_url:
        return None, None, (jsonify({"error": "URL is required"}), 400)
    if not original_url.startswith(("http://", "https://")):
        return None, None, (jsonify({"error": "URL must start with http:// or https://"}), 400)

    if user_id is not None and not isinstance(user_id, int):
        return None, None, (jsonify({"error": "Invalid user_id"}), 400)
    if title is not None and not isinstance(title, str):
        return None, None, (jsonify({"error": "Invalid title"}), 400)

    # Hint 3: validate user exists if provided
    if user_id is not None:
        if User.get_or_none(User.id == user_id) is None:
            return None, None, (jsonify({"error": "User not found"}), 404)

    # Hint 1: return existing record if same original_url + user_id already exists
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
            return None, None, (jsonify({"error": "Failed to generate a unique short code, please retry"}), 500)

        Event.create(
            url=url_record,
            user=user_id,
            event_type="created",
            details=json.dumps({"short_code": url_record.short_code, "original_url": original_url}),
        )
    except _DB_ERRORS:
        logger.exception("Database error creating URL")
        return None, None, _unavailable()

    return url_record, 201, None


@urls_bp.route("/shorten", methods=["POST"])
def shorten():
    err = _require_json()
    if err:
        return err
    data = request.get_json()
    raw_url = data.get("url")
    if not isinstance(raw_url, str):
        return jsonify({"error": "URL is required"}), 400
    original_url = raw_url.strip()
    url_record, status, err = _create_url(original_url, data.get("title"), data.get("user_id"))
    if err:
        return err
    return jsonify(_url_dict(url_record)), status


@urls_bp.route("/urls", methods=["POST"])
def create_url():
    err = _require_json()
    if err:
        return err
    data = request.get_json()
    raw_url = data.get("original_url")
    if not isinstance(raw_url, str):
        return jsonify({"error": "URL is required"}), 400
    original_url = raw_url.strip()
    url_record, status, err = _create_url(original_url, data.get("title"), data.get("user_id"))
    if err:
        return err
    return jsonify(_url_dict(url_record)), status


@urls_bp.route("/<short_code>", methods=["GET"])
def redirect_url(short_code):
    cache_hit = False
    cached = get_cached_url(short_code)

    if cached:
        original_url = cached["original_url"]
        is_active = cached["is_active"]
        url_id = cached.get("url_id")
        url_user_id = cached.get("url_user_id")
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
        url_id = url_record.id
        url_user_id = url_record.user_id
        cache_url(short_code, {
            "original_url": original_url,
            "is_active": is_active,
            "url_id": url_id,
            "url_user_id": url_user_id,
        })

    # Hint 4: check is_active BEFORE any tracking
    if not is_active:
        return jsonify({"error": "This URL is no longer active"}), 410

    # Increment click count and create click event (non-fatal)
    try:
        ShortenedURL.update(click_count=ShortenedURL.click_count + 1).where(
            ShortenedURL.short_code == short_code
        ).execute()
        # Hint 2: leave an event trail for every successful redirect
        Event.create(
            url=url_id,
            user=url_user_id,
            event_type="click",
            details=json.dumps({"short_code": short_code}),
        )
    except (IntegrityError, *_DB_ERRORS):
        logger.warning("Failed to record click for %s", short_code)

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

        return jsonify([_url_dict(u) for u in query]), 200
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
    return jsonify(_url_dict(url_record)), 200


@urls_bp.route("/urls/<int:url_id>", methods=["PUT"])
def update_url(url_id):
    err = _require_json()
    if err:
        return err
    try:
        url_record = ShortenedURL.get_by_id(url_id)
    except DoesNotExist:
        return jsonify({"error": "URL not found"}), 404
    except _DB_ERRORS:
        logger.exception("Database error in PUT /urls/%s", url_id)
        return _unavailable()

    data = request.get_json()
    try:
        if "title" in data:
            url_record.title = data["title"]
        if "original_url" in data:
            url_record.original_url = data["original_url"]
        if "is_active" in data:
            url_record.is_active = data["is_active"]
            if data["is_active"] is False:
                url_record.click_count = 0
                Event.delete().where(Event.url == url_record, Event.event_type == "click").execute()
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
    return jsonify(_url_dict(url_record)), 200


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
        url_record.click_count = 0
        url_record.save()
        Event.delete().where(Event.url == url_record, Event.event_type == "click").execute()
        Event.create(url=url_record, event_type="deleted")
    except _DB_ERRORS:
        logger.exception("Database error saving DELETE /urls/%s", url_id)
        return _unavailable()

    invalidate_url(url_record.short_code)
    return jsonify({"message": "URL deleted"}), 200
