import uuid

from fastapi.testclient import TestClient
from pymongo import MongoClient
from pytest import MonkeyPatch

from app.core.config import settings
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email


def test_create_conversation(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    payload = {"title": "Mi primera conversación"}
    response = client.post(
        f"{settings.API_V1_STR}/chats/",
        headers=normal_user_token_headers,
        json=payload,
    )
    assert response.status_code == 200
    content = response.json()
    assert content["title"] == payload["title"]
    assert "id" in content
    assert "created_at" in content
    assert "updated_at" in content


def test_list_conversations(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    payload = {"title": "Conversación para listar"}
    create_response = client.post(
        f"{settings.API_V1_STR}/chats/",
        headers=normal_user_token_headers,
        json=payload,
    )
    assert create_response.status_code == 200

    response = client.get(
        f"{settings.API_V1_STR}/chats/",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    assert content["count"] >= 1
    assert any(item["title"] == payload["title"] for item in content["data"])


def test_send_message_to_chat(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    db: MongoClient,
    monkeypatch: MonkeyPatch,
) -> None:
    create_response = client.post(
        f"{settings.API_V1_STR}/chats/",
        headers=normal_user_token_headers,
        json={"title": "Chat IA"},
    )
    assert create_response.status_code == 200
    conversation_id = create_response.json()["id"]

    async def mock_generate_chat_response(**_: object) -> str:
        return "Respuesta simulada de la IA"

    monkeypatch.setattr(
        "app.api.routes.chats.generate_chat_response",
        mock_generate_chat_response,
    )

    payload = {
        "message": "Hola IA",
        "provider": "openai",
        "model": "gpt-4o-mini",
        "temperature": 0.2,
    }
    response = client.post(
        f"{settings.API_V1_STR}/chats/{conversation_id}/messages",
        headers=normal_user_token_headers,
        json=payload,
    )
    assert response.status_code == 200
    content = response.json()
    assert content["conversation"]["id"] == conversation_id
    assert content["user_message"]["role"] == "user"
    assert content["assistant_message"]["role"] == "assistant"
    assert content["assistant_message"]["content"] == "Respuesta simulada de la IA"

    database = db[settings.MONGODB_DB]
    messages = list(
        database.messages.find({"conversation_id": uuid.UUID(conversation_id)})
    )
    assert len(messages) == 2


def test_transcribe_chat_audio(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    monkeypatch: MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def mock_transcribe_audio(**kwargs: object) -> str:
        captured.update(kwargs)
        return "Hola desde audio"

    monkeypatch.setattr(
        "app.api.routes.chats.transcribe_audio",
        mock_transcribe_audio,
    )

    response = client.post(
        f"{settings.API_V1_STR}/chats/audio/transcriptions",
        headers=normal_user_token_headers,
        files={
            "audio": (
                "recording.webm",
                b"fake audio",
                "audio/webm;codecs=opus",
            )
        },
    )

    assert response.status_code == 200
    assert response.json() == {"text": "Hola desde audio"}
    assert captured["content_type"] == "audio/webm"


def test_transcribe_chat_audio_rejects_unsupported_format(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    response = client.post(
        f"{settings.API_V1_STR}/chats/audio/transcriptions",
        headers=normal_user_token_headers,
        files={"audio": ("recording.txt", b"not audio", "text/plain")},
    )

    assert response.status_code == 400


def test_send_message_forbidden_for_non_owner(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    db: MongoClient,
) -> None:
    create_response = client.post(
        f"{settings.API_V1_STR}/chats/",
        headers=normal_user_token_headers,
        json={"title": "Privado"},
    )
    assert create_response.status_code == 200
    conversation_id = create_response.json()["id"]
    other_user_headers = authentication_token_from_email(
        client=client, email=random_email(), db=db
    )

    payload = {
        "message": "No deberías leer esto",
        "provider": "openai",
        "model": "gpt-4o-mini",
        "temperature": 0.2,
    }
    response = client.post(
        f"{settings.API_V1_STR}/chats/{conversation_id}/messages",
        headers=other_user_headers,
        json=payload,
    )
    assert response.status_code == 403
