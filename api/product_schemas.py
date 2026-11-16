"""Account and conversation wire contracts; tokens are returned only when issued."""

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from api.catalog_schemas import HeritageView
from api.schemas import Contract


class RegisterBody(Contract):
    email: str = Field(min_length=3, max_length=254)
    display_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        value = value.strip().casefold()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Invalid email")
        return value

    @field_validator("display_name")
    @classmethod
    def valid_name(cls, value):
        if not value.strip():
            raise ValueError("Display name is required")
        return value.strip()


class LoginBody(Contract):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class RefreshBody(Contract):
    refresh_token: str = Field(min_length=20, max_length=200)


class AccountView(Contract):
    account_id: UUID
    display_name: str
    email: str
    role: Literal["user", "editor", "admin"]
    disabled: bool
    version: int
    created_at: datetime


class AuthView(Contract):
    account: AccountView
    session_id: UUID
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    refresh_expires_at: datetime


class ProfilePatch(Contract):
    display_name: str = Field(min_length=1, max_length=80)
    version: int = Field(ge=1)

    _name = field_validator("display_name")(RegisterBody.valid_name.__func__)


class RoleBody(Contract):
    role: Literal["user", "editor", "admin"]
    version: int = Field(ge=1)
    disabled: bool = False


class PasswordBody(Contract):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class ConversationCreate(Contract):
    title: str = Field(default="Hội thoại mới", min_length=1, max_length=160)
    memory_enabled: bool = False


class ConversationPatch(Contract):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    memory_enabled: bool | None = None
    archived: bool | None = None
    version: int = Field(ge=1)


class ConversationView(Contract):
    conversation_id: UUID
    title: str
    memory_enabled: bool
    archived: bool
    version: int
    created_at: datetime
    updated_at: datetime


class ConversationPage(Contract):
    items: list[ConversationView]
    total: int
    limit: int
    offset: int


class MessageView(Contract):
    message_id: UUID
    turn_id: UUID
    run_id: UUID
    position: int
    role: Literal["user", "assistant"]
    content: str
    provenance: dict
    created_at: datetime


class MessagePage(Contract):
    items: list[MessageView]
    total: int
    limit: int
    offset: int


class FavoriteView(Contract):
    heritage_id: str
    created_at: datetime
    heritage: HeritageView


class FavoritePage(Contract):
    items: list[FavoriteView]
    total: int
    limit: int
    offset: int
