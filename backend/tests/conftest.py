from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient

from app.core.config import settings
from app.main import app
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import get_superuser_token_headers


@pytest.fixture(scope="session", autouse=True)
def db() -> Generator[MongoClient, None, None]:
    mongo_client = MongoClient(settings.MONGODB_URL, uuidRepresentation="standard")
    yield mongo_client
    database = mongo_client[settings.MONGODB_DB]
    database.messages.delete_many({})
    database.conversations.delete_many({})
    database.countries.delete_many({})
    database.users.delete_many({})
    mongo_client.close()


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def superuser_token_headers(client: TestClient) -> dict[str, str]:
    return get_superuser_token_headers(client)


@pytest.fixture(scope="module")
def normal_user_token_headers(
    client: TestClient, db: MongoClient
) -> dict[str, str]:
    return authentication_token_from_email(
        client=client, email=settings.EMAIL_TEST_USER, db=db
    )
