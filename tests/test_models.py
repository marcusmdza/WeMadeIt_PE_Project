import pytest
from peewee import IntegrityError

from app.models.event import Event
from app.models.url import ShortenedURL
from app.models.user import User


def test_create_user(test_app, seed_data):
    user = User.create(username="newuser", email="new@example.com")
    assert user.id is not None
    assert user.username == "newuser"


def test_create_url(test_app, seed_data):
    url = ShortenedURL.create(
        short_code="abc123",
        original_url="https://pytest.org",
    )
    assert url.short_code == "abc123"
    assert url.original_url == "https://pytest.org"


def test_short_code_unique(test_app, seed_data):
    ShortenedURL.create(short_code="dup001", original_url="https://first.com")
    with pytest.raises(IntegrityError):
        ShortenedURL.create(short_code="dup001", original_url="https://second.com")


def test_url_defaults(test_app, seed_data):
    url = ShortenedURL.create(
        short_code="def001",
        original_url="https://defaults.example.com",
    )
    assert url.is_active is True
    assert url.title is None


def test_create_event(test_app, seed_data):
    user = seed_data["user"]
    url = seed_data["active_url"]
    event = Event.create(url=url, user=user, event_type="click")
    assert event.event_type == "click"
