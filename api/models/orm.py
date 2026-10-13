"""Database tables. Only distilled facts are stored; chat history is never persisted."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


def utcnow() -> datetime:
    """Naive UTC timestamp (works identically on SQLite and Postgres)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class UserProfile(Base):
    """Distilled long-term memory: diet, address, taste and frequently bought items."""

    __tablename__ = "user_profiles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    diet: Mapped[str] = mapped_column(String(10), default="any")  # veg | non-veg | any
    spice_level: Mapped[int] = mapped_column(Integer, default=1)  # 0..3
    cuisines: Mapped[str] = mapped_column(Text, default="[]")  # JSON list
    frequent_items: Mapped[str] = mapped_column(Text, default="{}")  # JSON {item_id: count}
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    items: Mapped[str] = mapped_column(Text)  # JSON list
    total: Mapped[int] = mapped_column(Integer)
    address: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="placed")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SessionState(Base):
    """Short-lived conversation state (cart, pending confirmation). Expires automatically."""

    __tablename__ = "session_states"

    session_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    data: Mapped[str] = mapped_column(Text, default="{}")
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
