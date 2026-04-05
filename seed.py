import csv

from peewee import chunked

from app import create_app
from app.database import db
from app.models.event import Event
from app.models.url import ShortenedURL
from app.models.user import User


def load_csv(filepath):
    with open(filepath, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def seed():
    create_app()  # calls load_dotenv() and initialises the db proxy

    db.connect(reuse_if_open=True)
    try:
        # Drop in FK-safe order, recreate in reverse
        db.drop_tables([Event, ShortenedURL, User], safe=True)
        db.create_tables([User, ShortenedURL, Event])

        # --- Users ---
        users = load_csv("seeds/users.csv")
        with db.atomic():
            for batch in chunked(users, 100):
                User.insert_many(batch).execute()
        print(f"Users loaded: {len(users)}")

        # --- ShortenedURLs ---
        urls = load_csv("seeds/urls.csv")
        for row in urls:
            row["is_active"] = row["is_active"].strip().lower() in ("true", "1", "yes")
        with db.atomic():
            for batch in chunked(urls, 100):
                ShortenedURL.insert_many(batch).execute()
        print(f"ShortenedURLs loaded: {len(urls)}")

        # --- Events ---
        events = load_csv("seeds/events.csv")
        with db.atomic():
            for batch in chunked(events, 100):
                Event.insert_many(batch).execute()
        print(f"Events loaded: {len(events)}")

        # Reset sequences to avoid PK conflicts after bulk insert
        db.execute_sql("SELECT setval(pg_get_serial_sequence('\"user\"', 'id'), (SELECT MAX(id) FROM \"user\"))")
        db.execute_sql("SELECT setval(pg_get_serial_sequence('\"shortenedurl\"', 'id'), (SELECT MAX(id) FROM \"shortenedurl\"))")
        db.execute_sql("SELECT setval(pg_get_serial_sequence('\"event\"', 'id'), (SELECT MAX(id) FROM \"event\"))")
        print("Sequences reset")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
