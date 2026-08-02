import uuid

from fastapi.testclient import TestClient
from pymongo import MongoClient

from app.core.config import settings
from tests.utils.item import create_random_country


def test_create_country(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    data = {
        "name": "Bolivia",
        "alpha_2": "BO",
    }
    response = client.post(
        f"{settings.API_V1_STR}/countries/",
        headers=superuser_token_headers,
        json=data,
    )
    assert response.status_code == 200
    content = response.json()
    assert content["name"] == data["name"]
    assert content["alpha_2"] == data["alpha_2"]
    assert content["iso_numeric"] is None
    assert content["custom_data"] == {}
    assert "id" in content
    assert "owner_id" in content


def test_read_country(
    client: TestClient, superuser_token_headers: dict[str, str], db: MongoClient
) -> None:
    country = create_random_country(db)
    response = client.get(
        f"{settings.API_V1_STR}/countries/{country.id}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    assert content["name"] == country.country_name
    assert content["alpha_2"] == country.alpha_2
    assert content["iso_numeric"] == country.iso_numeric
    assert content["custom_data"] == country.custom_data
    assert content["id"] == str(country.id)
    assert content["owner_id"] == str(country.owner_id)


def test_read_country_not_found(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    response = client.get(
        f"{settings.API_V1_STR}/countries/{uuid.uuid4()}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 404
    content = response.json()
    assert content["detail"] == "Country not found"


def test_read_country_not_enough_permissions(
    client: TestClient, normal_user_token_headers: dict[str, str], db: MongoClient
) -> None:
    country = create_random_country(db)
    response = client.get(
        f"{settings.API_V1_STR}/countries/{country.id}",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 403
    content = response.json()
    assert content["detail"] == "Not enough permissions"


def test_read_countries(
    client: TestClient, superuser_token_headers: dict[str, str], db: MongoClient
) -> None:
    create_random_country(db)
    create_random_country(db)
    response = client.get(
        f"{settings.API_V1_STR}/countries/",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    assert len(content["data"]) >= 2


def test_update_country(
    client: TestClient, superuser_token_headers: dict[str, str], db: MongoClient
) -> None:
    country = create_random_country(db)
    data = {
        "name": "Bolivia Updated",
        "alpha_2": "BO",
        "iso_numeric": "068",
        "custom_data": {"some_new_key": 456},
    }
    response = client.put(
        f"{settings.API_V1_STR}/countries/{country.id}",
        headers=superuser_token_headers,
        json=data,
    )
    assert response.status_code == 200
    content = response.json()
    assert content["name"] == data["name"]
    assert content["alpha_2"] == data["alpha_2"]
    assert content["iso_numeric"] == data["iso_numeric"]
    assert content["custom_data"] == data["custom_data"]
    assert content["id"] == str(country.id)
    assert content["owner_id"] == str(country.owner_id)


def test_update_country_not_found(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    data = {"iso_numeric": "068"}
    response = client.put(
        f"{settings.API_V1_STR}/countries/{uuid.uuid4()}",
        headers=superuser_token_headers,
        json=data,
    )
    assert response.status_code == 404
    content = response.json()
    assert content["detail"] == "Country not found"


def test_create_countries_bulk_skips_existing(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    data = {
        "countries": [
            {"name": "Bulkland", "alpha_2": "XZ", "iso_numeric": "901"},
            {"name": "Bulkland duplicate", "alpha_2": "XZ", "iso_numeric": "901"},
            {"name": "Bulkshire", "alpha_2": "XY", "iso_numeric": "902"},
        ]
    }
    response = client.post(
        f"{settings.API_V1_STR}/countries/bulk",
        headers=superuser_token_headers,
        json=data,
    )
    assert response.status_code == 200
    content = response.json()
    assert len(content["created"]) == 2
    assert len(content["skipped"]) == 1
    assert {country["alpha_2"] for country in content["created"]} == {"XZ", "XY"}
    assert content["skipped"][0]["alpha_2"] == "XZ"


def test_update_country_not_enough_permissions(
    client: TestClient, normal_user_token_headers: dict[str, str], db: MongoClient
) -> None:
    country = create_random_country(db)
    data = {"iso_numeric": "068"}
    response = client.put(
        f"{settings.API_V1_STR}/countries/{country.id}",
        headers=normal_user_token_headers,
        json=data,
    )
    assert response.status_code == 403
    content = response.json()
    assert content["detail"] == "Not enough permissions"


def test_delete_country(
    client: TestClient, superuser_token_headers: dict[str, str], db: MongoClient
) -> None:
    country = create_random_country(db)
    response = client.delete(
        f"{settings.API_V1_STR}/countries/{country.id}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    assert content["message"] == "Country deleted successfully"


def test_delete_country_not_found(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    response = client.delete(
        f"{settings.API_V1_STR}/countries/{uuid.uuid4()}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 404
    content = response.json()
    assert content["detail"] == "Country not found"


def test_delete_country_not_enough_permissions(
    client: TestClient, normal_user_token_headers: dict[str, str], db: MongoClient
) -> None:
    country = create_random_country(db)
    response = client.delete(
        f"{settings.API_V1_STR}/countries/{country.id}",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 403
    content = response.json()
    assert content["detail"] == "Not enough permissions"
