"""
Test infrastructure for the Flask + Peewee app.

Prerequisites:
    createdb hackathon_test_db

Run tests:
    uv run pytest
    uv run pytest --cov=app
"""

import os

import pytest
from peewee import PostgresqlDatabase

from app.models.event import Event
from app.models.url import ShortenedURL
from app.models.user import User

TABLES = [User, ShortenedURL, Event]


@pytest.fixture(scope="session")
def test_app():
    """Create the Flask app wired to hackathon_test_db for the whole test session."""
    # Override DATABASE_NAME before create_app() calls init_db(), so the proxy
    # is initialised pointing at the test database, not the production one.
    os.environ["DATABASE_NAME"] = "hackathon_test_db"

    from app import create_app
    from app.database import db

    app = create_app()
    app.config["TESTING"] = True

    db.connect(reuse_if_open=True)
    db.create_tables(TABLES)
    db.close()

    yield app

    db.connect(reuse_if_open=True)
    db.drop_tables(TABLES, safe=True)
    db.close()


@pytest.fixture()
def client(test_app):
    """Flask test client."""
    return test_app.test_client()


@pytest.fixture()
def seed_data(test_app):
    """Insert a sample user and two URLs; clean up after each test."""
    from app.database import db

    db.connect(reuse_if_open=True)

    user = User.create(username="testuser", email="test@example.com")

    active_url = ShortenedURL.create(
        user=user,
        short_code="test01",
        original_url="https://example.com",
        is_active=True,
    )
    inactive_url = ShortenedURL.create(
        user=user,
        short_code="dead01",
        original_url="https://dead.example.com",
        is_active=False,
    )

    db.close()

    yield {"user": user, "active_url": active_url, "inactive_url": inactive_url}

    # Teardown: delete all rows in FK-safe order so each test starts clean.
    db.connect(reuse_if_open=True)
    Event.delete().execute()
    ShortenedURL.delete().execute()
    User.delete().execute()
    db.close()
