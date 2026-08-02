import uuid
from datetime import datetime, timezone

from pymongo import MongoClient

from app.core.config import settings
from app.models import Country
from tests.utils.user import create_random_user
from tests.utils.utils import random_lower_string


def create_random_country(db: MongoClient) -> Country:
    user = create_random_user(db)
    owner_id = user.id
    assert owner_id is not None
    database = db[settings.MONGODB_DB]
    country_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    country_doc = {
        "_id": country_id,
        "country_name": random_lower_string(),
        "alpha_2": "BO",
        "iso_numeric": "068",
        "custom_data": {"example_key": 123},
        "owner_id": owner_id,
        "created_at": now,
    }
    database.countries.insert_one(country_doc)
    return Country(
        id=country_id,
        country_name=country_doc["country_name"],
        alpha_2=country_doc["alpha_2"],
        iso_numeric=country_doc["iso_numeric"],
        custom_data=country_doc["custom_data"],
        owner_id=owner_id,
        created_at=now,
    )
