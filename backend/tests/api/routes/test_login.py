import uuid
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from pwdlib.hashers.bcrypt import BcryptHasher
from pymongo import MongoClient

from app.core.config import settings
from app.core.security import get_password_hash, verify_password
from app.utils import generate_password_reset_token
from tests.utils.user import user_authentication_headers
from tests.utils.utils import random_email, random_lower_string


def test_get_access_token(client: TestClient) -> None:
    login_data = {
        "username": settings.FIRST_SUPERUSER,
        "password": settings.FIRST_SUPERUSER_PASSWORD,
    }
    r = client.post(f"{settings.API_V1_STR}/login/access-token", data=login_data)
    tokens = r.json()
    assert r.status_code == 200
    assert "access_token" in tokens
    assert tokens["access_token"]


def test_get_access_token_incorrect_password(client: TestClient) -> None:
    login_data = {
        "username": settings.FIRST_SUPERUSER,
        "password": "incorrect",
    }
    r = client.post(f"{settings.API_V1_STR}/login/access-token", data=login_data)
    assert r.status_code == 400


def test_use_access_token(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    r = client.post(
        f"{settings.API_V1_STR}/login/test-token",
        headers=superuser_token_headers,
    )
    result = r.json()
    assert r.status_code == 200
    assert "email" in result


def test_recovery_password(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    with (
        patch("app.core.config.settings.SMTP_HOST", "smtp.example.com"),
        patch("app.core.config.settings.SMTP_USER", "admin@example.com"),
    ):
        email = "test@example.com"
        r = client.post(
            f"{settings.API_V1_STR}/password-recovery/{email}",
            headers=normal_user_token_headers,
        )
        assert r.status_code == 200
        assert r.json() == {
            "message": "If that email is registered, we sent a password recovery link"
        }


def test_recovery_password_user_not_exits(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    email = "jVgQr@example.com"
    r = client.post(
        f"{settings.API_V1_STR}/password-recovery/{email}",
        headers=normal_user_token_headers,
    )
    assert r.status_code == 200
    assert r.json() == {
        "message": "If that email is registered, we sent a password recovery link"
    }


def test_reset_password(client: TestClient, db: MongoClient) -> None:
    database = db[settings.MONGODB_DB]
    email = random_email()
    password = random_lower_string()
    new_password = random_lower_string()

    user_id = uuid.uuid4()
    user_doc = {
        "_id": user_id,
        "email": email,
        "full_name": "Test User",
        "hashed_password": get_password_hash(password),
        "is_active": True,
        "is_superuser": False,
        "created_at": datetime.now(timezone.utc),
    }
    database.users.insert_one(user_doc)

    token = generate_password_reset_token(email=email)
    headers = user_authentication_headers(client=client, email=email, password=password)
    data = {"new_password": new_password, "token": token}

    r = client.post(
        f"{settings.API_V1_STR}/reset-password/",
        headers=headers,
        json=data,
    )

    assert r.status_code == 200
    assert r.json() == {"message": "Password updated successfully"}

    updated_doc = database.users.find_one({"_id": user_id})
    assert updated_doc
    verified, _ = verify_password(new_password, updated_doc["hashed_password"])
    assert verified


def test_reset_password_invalid_token(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    data = {"new_password": "changethis", "token": "invalid"}
    r = client.post(
        f"{settings.API_V1_STR}/reset-password/",
        headers=superuser_token_headers,
        json=data,
    )
    response = r.json()

    assert "detail" in response
    assert r.status_code == 400
    assert response["detail"] == "Invalid token"


def test_login_with_bcrypt_password_upgrades_to_argon2(
    client: TestClient, db: MongoClient
) -> None:
    """Test that logging in with a bcrypt password hash upgrades it to argon2."""
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
    tokens = r.json()
    assert "access_token" in tokens

    updated_doc = database.users.find_one({"_id": user_id})
    assert updated_doc
    assert updated_doc["hashed_password"].startswith("$argon2")

    verified, updated_hash = verify_password(password, updated_doc["hashed_password"])
    assert verified
    assert updated_hash is None


def test_login_with_argon2_password_keeps_hash(client: TestClient, db: MongoClient) -> None:
    """Test that logging in with an argon2 password hash does not update it."""
    database = db[settings.MONGODB_DB]
    email = random_email()
    password = random_lower_string()

    argon2_hash = get_password_hash(password)
    assert argon2_hash.startswith("$argon2")

    user_id = uuid.uuid4()
    user_doc = {
        "_id": user_id,
        "email": email,
        "hashed_password": argon2_hash,
        "is_active": True,
        "is_superuser": False,
        "full_name": None,
        "created_at": datetime.now(timezone.utc),
    }
    database.users.insert_one(user_doc)

    original_hash = argon2_hash

    login_data = {"username": email, "password": password}
    r = client.post(f"{settings.API_V1_STR}/login/access-token", data=login_data)
    assert r.status_code == 200
    tokens = r.json()
    assert "access_token" in tokens

    updated_doc = database.users.find_one({"_id": user_id})
    assert updated_doc
    assert updated_doc["hashed_password"] == original_hash
    assert updated_doc["hashed_password"].startswith("$argon2")
