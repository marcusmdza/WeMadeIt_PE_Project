import csv
import io
import logging

from flask import Blueprint, jsonify, request
from peewee import DatabaseError, DoesNotExist, chunked
from playhouse.shortcuts import model_to_dict

from app.database import db
from app.models.user import User

users_bp = Blueprint("users", __name__)
logger = logging.getLogger(__name__)


def _unavailable():
    return jsonify({"error": "Service temporarily unavailable"}), 503


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
    except DatabaseError:
        logger.exception("Database error in GET /users")
        return _unavailable()


@users_bp.route("/users/<int:user_id>", methods=["GET"])
def get_user(user_id):
    try:
        user = User.get_by_id(user_id)
    except DoesNotExist:
        return jsonify({"error": "User not found"}), 404
    except DatabaseError:
        logger.exception("Database error in GET /users/%s", user_id)
        return _unavailable()
    return jsonify(model_to_dict(user, backrefs=False)), 200


@users_bp.route("/users", methods=["POST"])
def create_user():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    email = data.get("email", "").strip()

    if not username:
        return jsonify({"error": "username is required"}), 400
    if not email:
        return jsonify({"error": "email is required"}), 400

    try:
        user = User.create(username=username, email=email)
    except DatabaseError:
        logger.exception("Database error in POST /users")
        return _unavailable()

    return jsonify(model_to_dict(user, backrefs=False)), 201


@users_bp.route("/users/<int:user_id>", methods=["PUT"])
def update_user(user_id):
    try:
        user = User.get_by_id(user_id)
    except DoesNotExist:
        return jsonify({"error": "User not found"}), 404
    except DatabaseError:
        logger.exception("Database error in PUT /users/%s", user_id)
        return _unavailable()

    data = request.get_json(silent=True) or {}
    try:
        if "username" in data:
            user.username = data["username"]
        if "email" in data:
            user.email = data["email"]
        user.save()
    except DatabaseError:
        logger.exception("Database error saving PUT /users/%s", user_id)
        return _unavailable()

    return jsonify(model_to_dict(user, backrefs=False)), 200


@users_bp.route("/users/<int:user_id>", methods=["DELETE"])
def delete_user(user_id):
    try:
        user = User.get_by_id(user_id)
    except DoesNotExist:
        return jsonify({"error": "User not found"}), 404
    except DatabaseError:
        logger.exception("Database error in DELETE /users/%s", user_id)
        return _unavailable()

    try:
        user.delete_instance()
    except DatabaseError:
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
    except DatabaseError:
        logger.exception("Database error in POST /users/bulk")
        return _unavailable()

    return jsonify({"message": f"{len(rows)} users loaded"}), 201
