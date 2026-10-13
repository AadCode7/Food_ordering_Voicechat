"""Request / response models (pydantic)."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SESSION = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


class SignUpIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL.match(v):
            raise ValueError("Enter a valid email address")
        return v

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name is required")
        return v


class SignInIn(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return v.strip().lower()


class UserOut(BaseModel):
    id: int
    name: str
    email: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ProfileIn(BaseModel):
    address: str | None = Field(default=None, max_length=300)
    diet: Literal["veg", "non-veg", "any"] | None = None
    spice_level: int | None = Field(default=None, ge=0, le=3)
    cuisines: list[str] | None = Field(default=None, max_length=10)


class ProfileOut(BaseModel):
    address: str | None
    diet: str
    spice_level: int
    cuisines: list[str]
    frequent_items: dict[str, int]


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    session_id: str | None = None

    @field_validator("session_id")
    @classmethod
    def _sid(cls, v: str | None) -> str | None:
        if v is not None and not _SESSION.match(v):
            raise ValueError("session_id must be 8-64 chars of letters, digits, _ or -")
        return v


class ChatOut(BaseModel):
    reply: str
    intent: str
    source: str
    session_id: str
    cart: list[dict]
    total: int
    suggestions: list[dict]
    order: dict | None = None
    latency_ms: int
