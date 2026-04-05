import datetime

from peewee import AutoField, BooleanField, CharField, DateTimeField, ForeignKeyField, IntegerField, TextField

from app.database import BaseModel
from app.models.user import User


class ShortenedURL(BaseModel):
    id = AutoField(primary_key=True)
    user = ForeignKeyField(User, backref='urls', null=True)
    short_code = CharField(unique=True, max_length=20, index=True)
    original_url = TextField()
    title = CharField(max_length=255, null=True)
    is_active = BooleanField(default=True)
    click_count = IntegerField(default=0)
    created_at = DateTimeField(default=datetime.datetime.now)
    updated_at = DateTimeField(default=datetime.datetime.now)
