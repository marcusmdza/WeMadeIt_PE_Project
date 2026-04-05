import datetime

from peewee import AutoField, CharField, DateTimeField, ForeignKeyField, TextField

from app.database import BaseModel
from app.models.url import ShortenedURL
from app.models.user import User


class Event(BaseModel):
    id = AutoField(primary_key=True)
    url = ForeignKeyField(ShortenedURL, backref='events', null=True)
    user = ForeignKeyField(User, backref='events', null=True)
    event_type = CharField(max_length=50)
    timestamp = DateTimeField(default=datetime.datetime.now)
    details = TextField(null=True)
