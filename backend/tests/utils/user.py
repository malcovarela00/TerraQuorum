import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from pymongo import MongoClient

from app.core.config import settings
from app.core.security import get_password_hash
from app.models import User
from tests.utils.utils import random_email, random_lower_string


def user_authentication_headers(
    *, client: TestClient, email: str, password: str
) -> dict[str, str]:
    data = {"username": email, "password": password}

    r = client.post(f"{settings.API_V1_STR}/login/access-token", data=data)
    response = r.json()
    auth_token = response["access_token"]
    headers = {"Authorization": f"Bearer {auth_token}"}
    return headers


def create_random_user(db: MongoClient) -> User:
    database = db[settings.MONGODB_DB]
    email = random_email()
    password = random_lower_string()
    user_id = uuid.uuid4()
    user_doc = {
        "_id": user_id,
        "email": email,
        "hashed_password": get_password_hash(password),
        "is_active": True,
        "is_superuser": False,
        "full_name": None,
        "created_at": datetime.now(timezone.utc),
    }
    database.users.insert_one(user_doc)
    return User(
        id=user_id,
        email=email,
        hashed_password=user_doc["hashed_password"],
        is_active=True,
        is_superuser=False,
        full_name=None,
        created_at=user_doc["created_at"],
    )


def authentication_token_from_email(
    *, client: TestClient, email: str, db: MongoClient
) -> dict[str, str]:
    """
    Return a valid token for the user with given email.

    If the user doesn't exist it is created first.
    """
    database = db[settings.MONGODB_DB]
    password = random_lower_string()
    user_doc = database.users.find_one({"email": email})
    if not user_doc:
        user_id = uuid.uuid4()
        new_user = {
            "_id": user_id,
            "email": email,
            "hashed_password": get_password_hash(password),
            "is_active": True,
            "is_superuser": False,
            "full_name": None,
            "created_at": datetime.now(timezone.utc),
        }
        database.users.insert_one(new_user)
    else:
        database.users.update_one(
            {"email": email},
            {"$set": {"hashed_password": get_password_hash(password)}},
        )

    return user_authentication_headers(client=client, email=email, password=password)
