import asyncio
from typing import Any

from beanie import init_beanie
from pymongo import AsyncMongoClient

from app import crud
from app.core.config import settings
from app.models import (
    ChatConversation,
    ChatMessageDB,
    Country,
    User,
    UserCreate,
)

clients_by_loop: dict[asyncio.AbstractEventLoop, AsyncMongoClient] = {}


async def _get_database() -> Any:
    current_loop = asyncio.get_running_loop()
    client = clients_by_loop.get(current_loop)
    if client is None:
        client = AsyncMongoClient(settings.MONGODB_URL)
        clients_by_loop[current_loop] = client
    return client[settings.MONGODB_DB]


async def init_db() -> None:
    database = await _get_database()
    await init_beanie(
        database=database,
        document_models=[User, Country, ChatConversation, ChatMessageDB],
    )

    user = await User.find_one(User.email == settings.FIRST_SUPERUSER)
    if not user:
        user_in = UserCreate(
            email=settings.FIRST_SUPERUSER,
            password=settings.FIRST_SUPERUSER_PASSWORD,
            is_superuser=True,
        )
        await crud.create_user(user_create=user_in)
