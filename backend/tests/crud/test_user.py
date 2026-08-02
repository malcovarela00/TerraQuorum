import uuid
from datetime import datetime, timezone

from pymongo import MongoClient
from pwdlib.hashers.bcrypt import BcryptHasher

from app.core.config import settings
from app.core.security import get_password_hash, verify_password
from tests.utils.utils import random_email, random_lower_string


def test_create_user(client, db: MongoClient) -> None:
    database = db[settings.MONGODB_DB]
    email = random_email()
    password = random_lower_string()
    data = {"email": email, "password": password}
    r = client.post(
        f"{settings.API_V1_STR}/users/signup",
        json=data,
    )
    assert r.status_code == 200
    created = r.json()
    assert created["email"] == email

    user_doc = database.users.find_one({"email": email})
    assert user_doc is not None
    assert user_doc["email"] == email
    assert "hashed_password" in user_doc


def test_authenticate_user(client, db: MongoClient) -> None:
    email = random_email()
    password = random_lower_string()
    data = {"email": email, "password": password}
    r = client.post(f"{settings.API_V1_STR}/users/signup", json=data)
    assert r.status_code == 200

    login_data = {"username": email, "password": password}
    r = client.post(f"{settings.API_V1_STR}/login/access-token", data=login_data)
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_not_authenticate_user(client) -> None:
    email = random_email()
    password = random_lower_string()
    login_data = {"username": email, "password": password}
    r = client.post(f"{settings.API_V1_STR}/login/access-token", data=login_data)
    assert r.status_code == 400


def test_check_if_user_is_active(client, db: MongoClient) -> None:
    database = db[settings.MONGODB_DB]
    email = random_email()
    password = random_lower_string()
    data = {"email": email, "password": password}
    r = client.post(f"{settings.API_V1_STR}/users/signup", json=data)
    assert r.status_code == 200

    user_doc = database.users.find_one({"email": email})
    assert user_doc is not None
    assert user_doc["is_active"] is True


def test_check_if_user_is_superuser(
    client, superuser_token_headers: dict[str, str], db: MongoClient
) -> None:
    database = db[settings.MONGODB_DB]
    email = random_email()
    password = random_lower_string()
    data = {"email": email, "password": password, "is_superuser": True}
    r = client.post(
        f"{settings.API_V1_STR}/users/",
        headers=superuser_token_headers,
        json=data,
    )
    assert 200 <= r.status_code < 300

    user_doc = database.users.find_one({"email": email})
    assert user_doc is not None
    assert user_doc["is_superuser"] is True


def test_check_if_user_is_superuser_normal_user(client, db: MongoClient) -> None:
    database = db[settings.MONGODB_DB]
    email = random_email()
    password = random_lower_string()
    data = {"email": email, "password": password}
    r = client.post(f"{settings.API_V1_STR}/users/signup", json=data)
    assert r.status_code == 200

    user_doc = database.users.find_one({"email": email})
    assert user_doc is not None
    assert user_doc["is_superuser"] is False


def test_get_user(client, superuser_token_headers: dict[str, str]) -> None:
    email = random_email()
    password = random_lower_string()
    data = {"email": email, "password": password}
    r = client.post(
        f"{settings.API_V1_STR}/users/",
        headers=superuser_token_headers,
        json=data,
    )
    assert 200 <= r.status_code < 300
    created = r.json()
    user_id = created["id"]

    r = client.get(
        f"{settings.API_V1_STR}/users/{user_id}",
        headers=superuser_token_headers,
    )
    assert r.status_code == 200
    api_user = r.json()
    assert api_user["email"] == email


def test_update_user(client, superuser_token_headers: dict[str, str], db: MongoClient) -> None:
    database = db[settings.MONGODB_DB]
    email = random_email()
    password = random_lower_string()
    data = {"email": email, "password": password}
    r = client.post(
        f"{settings.API_V1_STR}/users/",
        headers=superuser_token_headers,
        json=data,
    )
    assert 200 <= r.status_code < 300
    created = r.json()
    user_id = created["id"]

    new_password = random_lower_string()
    update_data = {"password": new_password, "is_superuser": True}
    r = client.patch(
        f"{settings.API_V1_STR}/users/{user_id}",
        headers=superuser_token_headers,
        json=update_data,
    )
    assert r.status_code == 200

    user_doc = database.users.find_one({"_id": uuid.UUID(user_id)})
    assert user_doc is not None
    assert user_doc["email"] == email
    verified, _ = verify_password(new_password, user_doc["hashed_password"])
    assert verified


def test_authenticate_user_with_bcrypt_upgrades_to_argon2(
    client, db: MongoClient
) -> None:
    database = db[settings.MONGODB_DB]
    email = random_email()
    password = random_lower_string()

    bcrypt_hasher = BcryptHasher()
    bcrypt_hash = bcrypt_hasher.hash(password)
    assert bcrypt_hash.startswith("$2")

    user_id = uuid.uuid4()
    user_doc = {
        "_id": user_id,
        "email": email,
        "hashed_password": bcrypt_hash,
        "is_active": True,
        "is_superuser": False,
        "full_name": None,
        "created_at": datetime.now(timezone.utc),
    }
    database.users.insert_one(user_doc)

    login_data = {"username": email, "password": password}
    r = client.post(f"{settings.API_V1_STR}/login/access-token", data=login_data)
    assert r.status_code == 200
    assert "access_token" in r.json()

    updated_doc = database.users.find_one({"_id": user_id})
    assert updated_doc is not None
    assert updated_doc["hashed_password"].startswith("$argon2")

    verified, updated_hash = verify_password(password, updated_doc["hashed_password"])
    assert verified
    assert updated_hash is None
