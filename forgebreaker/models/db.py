"""
SQLAlchemy ORM models for persistent storage.

Models mirror the dataclass models but add database persistence.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


class UserCollectionDB(Base):
    """
    A user's card collection stored in the database.

    Each user has one collection containing their owned cards.
    """

    __tablename__ = "user_collections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationship to card ownership records
    cards: Mapped[list["CardOwnershipDB"]] = relationship(
        back_populates="collection", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<UserCollectionDB(id={self.id}, user_id={self.user_id})>"


class CardOwnershipDB(Base):
    """
    Individual card ownership record.

    Tracks how many copies of a specific card a user owns.
    """

    __tablename__ = "card_ownership"
    __table_args__ = (UniqueConstraint("collection_id", "card_name", name="uq_collection_card"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    collection_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user_collections.id", ondelete="CASCADE"), index=True
    )
    card_name: Mapped[str] = mapped_column(String(255), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)

    # Relationship back to collection
    collection: Mapped["UserCollectionDB"] = relationship(back_populates="cards")

    def __repr__(self) -> str:
        return f"<CardOwnershipDB(card={self.card_name}, qty={self.quantity})>"


class MetaDeckDB(Base):
    """
    A competitive meta deck stored in the database.

    Scraped from MTGGoldfish and cached for quick access.
    """

    __tablename__ = "meta_decks"
    __table_args__ = (UniqueConstraint("name", "format", name="uq_deck_name_format"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    archetype: Mapped[str] = mapped_column(String(50))
    format: Mapped[str] = mapped_column(String(50), index=True)

    # Deck contents stored as JSON for flexibility
    cards: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    sideboard: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    # Meta statistics
    win_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    meta_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<MetaDeckDB(name={self.name}, format={self.format})>"
