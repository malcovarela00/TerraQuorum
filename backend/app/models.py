import uuid
from datetime import datetime, timezone
from typing import Any

from beanie import Document
from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)


def get_datetime_utc() -> datetime:
    return datetime.now(timezone.utc)


def normalize_alpha_2(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    return normalized or None


# Shared properties
class UserBase(BaseModel):
    email: EmailStr = Field(max_length=255)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on creation
class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserRegister(BaseModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on update, all are optional
class UserUpdate(UserBase):
    email: EmailStr | None = Field(default=None, max_length=255)  # type: ignore
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserUpdateMe(BaseModel):
    full_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)


class UpdatePassword(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


# Database model
class User(Document):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)  # type: ignore[assignment]
    email: EmailStr
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = None
    hashed_password: str
    created_at: datetime = Field(default_factory=get_datetime_utc)

    class Settings:
        name = "users"


# Properties to return via API, id is always required
class UserPublic(UserBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime | None = None


class UsersPublic(BaseModel):
    data: list[UserPublic]
    count: int


# Shared properties
class CountryBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    country_name: str = Field(
        min_length=1,
        max_length=255,
        alias="name",
        validation_alias=AliasChoices("name", "country_name"),
    )
    alpha_2: str | None = Field(
        default=None,
        min_length=2,
        max_length=2,
        pattern=r"^[A-Z]{2}$",
    )
    iso_numeric: str | None = Field(default=None, max_length=3)
    custom_data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("alpha_2", mode="before")
    @classmethod
    def normalize_alpha_2_code(cls, value: str | None) -> str | None:
        return normalize_alpha_2(value)


# Properties to receive on country creation
class CountryCreate(CountryBase):
    pass


# Properties to receive on country update
class CountryUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    country_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        alias="name",
        validation_alias=AliasChoices("name", "country_name"),
    )
    alpha_2: str | None = Field(
        default=None,
        min_length=2,
        max_length=2,
        pattern=r"^[A-Z]{2}$",
    )
    iso_numeric: str | None = Field(default=None, max_length=3)
    custom_data: dict[str, Any] | None = None

    @field_validator("alpha_2", mode="before")
    @classmethod
    def normalize_alpha_2_code(cls, value: str | None) -> str | None:
        return normalize_alpha_2(value)


class CountryBulkCreate(BaseModel):
    countries: list[CountryCreate] = Field(min_length=1)


# Database model
class Country(Document):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)  # type: ignore[assignment]
    country_name: str
    alpha_2: str | None = None
    iso_numeric: str | None = None
    custom_data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=get_datetime_utc)
    owner_id: uuid.UUID

    class Settings:
        name = "countries"


class ChatConversationBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class ChatConversationCreate(ChatConversationBase):
    pass


class ChatConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)


class ChatConversation(Document):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)  # type: ignore[assignment]
    title: str
    created_at: datetime = Field(default_factory=get_datetime_utc)
    updated_at: datetime = Field(default_factory=get_datetime_utc)
    owner_id: uuid.UUID

    class Settings:
        name = "conversations"


class ChatConversationPublic(ChatConversationBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    owner_id: uuid.UUID
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ChatConversationsPublic(BaseModel):
    data: list[ChatConversationPublic]
    count: int


class ChatMessageBase(BaseModel):
    role: str = Field(min_length=1, max_length=32)
    content: str = Field(min_length=1)
    provider: str | None = Field(default=None, max_length=32)
    model: str | None = Field(default=None, max_length=255)


class ChatMessageDB(Document):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)  # type: ignore[assignment]
    role: str
    content: str
    provider: str | None = None
    model: str | None = None
    metadata: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=get_datetime_utc)
    conversation_id: uuid.UUID

    class Settings:
        name = "messages"


class ChatMessagePublic(ChatMessageBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    conversation_id: uuid.UUID
    metadata: dict[str, Any] | None = None
    created_at: datetime | None = None


class ChatMessagesPublic(BaseModel):
    data: list[ChatMessagePublic]
    count: int


class ChatCompletionCreate(BaseModel):
    message: str = Field(min_length=1)
    provider: str = Field(min_length=1, max_length=32)
    model: str = Field(min_length=1, max_length=255)
    system_prompt: str | None = Field(default=None, max_length=4000)
    temperature: float = Field(default=0.2, ge=0, le=2)


class ChatCompletionPublic(BaseModel):
    conversation: ChatConversationPublic
    user_message: ChatMessagePublic
    assistant_message: ChatMessagePublic


class ChatAudioTranscriptionPublic(BaseModel):
    text: str


# Properties to return via API, id is always required
class CountryPublic(CountryBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    owner_id: uuid.UUID
    created_at: datetime | None = None


class CountriesPublic(BaseModel):
    data: list[CountryPublic]
    count: int


class CountryBulkCreatePublic(BaseModel):
    created: list[CountryPublic]
    skipped: list[CountryCreate]


class CountryMapPoint(BaseModel):
    country_name: str
    alpha_2: str | None = None
    iso_numeric: str | None = None
    custom_data: dict[str, Any] = Field(default_factory=dict)


class CountryMapDataResponse(BaseModel):
    data: list[CountryMapPoint]
    available_keys: list[str]


# Generic message
class Message(BaseModel):
    message: str


# JSON payload containing access token
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# Contents of JWT token
class TokenPayload(BaseModel):
    sub: str | None = None


class NewPassword(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)
