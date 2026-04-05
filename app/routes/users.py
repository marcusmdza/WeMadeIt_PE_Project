import csv
import io
import logging

from flask import Blueprint, jsonify, request
from peewee import DoesNotExist, IntegrityError, InterfaceError, OperationalError, chunked
from playhouse.shortcuts import model_to_dict

from app.database import db
from app.models.user import User

users_bp = Blueprint("users", __name__)
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


def _validate_email(email):
    """Return an error response tuple if email is not valid, else None."""
    if "@" not in email:
        return jsonify({"error": "Invalid email format"}), 400
    local, _, domain = email.partition("@")
    if not local or "." not in domain:
        return jsonify({"error": "Invalid email format"}), 400
    return None


@users_bp.route("/users", methods=["GET"])
def list_users():
    try:
        query = User.select().order_by(User.id)
        page = request.args.get("page", type=int)
        per_page = request.args.get("per_page", type=int)

        if page is not None and per_page is not None:
            offset = (page - 1) * per_page
            query = query.limit(per_page).offset(offset)

        return jsonify([model_to_dict(u, backrefs=False) for u in query]), 200
    except _DB_ERRORS:
        logger.exception("Database error in GET /users")
        return _unavailable()


@users_bp.route("/users/<int:user_id>", methods=["GET"])
def get_user(user_id):
    try:
        user = User.get_by_id(user_id)
    except DoesNotExist:
        return jsonify({"error": "User not found"}), 404
    except _DB_ERRORS:
        logger.exception("Database error in GET /users/%s", user_id)
        return _unavailable()
    return jsonify(model_to_dict(user, backrefs=False)), 200


@users_bp.route("/users", methods=["POST"])
def create_user():
    err = _require_json()
    if err:
        return err
    data = request.get_json()
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip()

    if not username or not email:
        return jsonify({"error": "Username and email are required"}), 400

    err = _validate_email(email)
    if err:
        return err

    try:
        user = User.create(username=username, email=email)
    except IntegrityError:
        return jsonify({"error": "A user with that username or email already exists"}), 409
    except _DB_ERRORS:
        logger.exception("Database error in POST /users")
        return _unavailable()

    return jsonify(model_to_dict(user, backrefs=False)), 201


@users_bp.route("/users/<int:user_id>", methods=["PUT"])
def update_user(user_id):
    err = _require_json()
    if err:
        return err
    try:
        user = User.get_by_id(user_id)
    except DoesNotExist:
        return jsonify({"error": "User not found"}), 404
    except _DB_ERRORS:
        logger.exception("Database error in PUT /users/%s", user_id)
        return _unavailable()

    data = request.get_json()
    if "email" in data:
        err = _validate_email((data.get("email") or "").strip())
        if err:
            return err
    try:
        if "username" in data:
            user.username = data["username"]
        if "email" in data:
            user.email = data["email"]
        user.save()
    except IntegrityError:
        return jsonify({"error": "A user with that username or email already exists"}), 409
    except _DB_ERRORS:
        logger.exception("Database error saving PUT /users/%s", user_id)
        return _unavailable()

    return jsonify(model_to_dict(user, backrefs=False)), 200


@users_bp.route("/users/<int:user_id>", methods=["DELETE"])
def delete_user(user_id):
    try:
        user = User.get_by_id(user_id)
    except DoesNotExist:
        return jsonify({"error": "User not found"}), 404
    except _DB_ERRORS:
        logger.exception("Database error in DELETE /users/%s", user_id)
        return _unavailable()

    try:
        user.delete_instance()
    except _DB_ERRORS:
        logger.exception("Database error deleting /users/%s", user_id)
        return _unavailable()

    return jsonify({"message": "User deleted"}), 200


@users_bp.route("/users/bulk", methods=["POST"])
def bulk_load_users():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    try:
        content = file.read().decode("utf-8")
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
    except Exception:
        return jsonify({"error": "Could not parse CSV file"}), 400

    if not rows:
        return jsonify({"error": "CSV file is empty"}), 400

    try:
        with db.atomic():
            for batch in chunked(rows, 100):
                User.insert_many(batch).execute()
        db.execute_sql(
            'SELECT setval(pg_get_serial_sequence(\'\"user\"\', \'id\'), '
            '(SELECT COALESCE(MAX(id), 0) FROM "user"))'
        )
    except IntegrityError:
        return jsonify({"error": "Duplicate username or email in CSV"}), 409
    except _DB_ERRORS:
        logger.exception("Database error in POST /users/bulk")
        return _unavailable()

    count = len(rows)
    return jsonify({"message": f"{count} users loaded", "count": count}), 201
