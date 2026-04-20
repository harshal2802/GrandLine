from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base
from app.models.enums import VoyageStatus

if TYPE_CHECKING:
    from app.models.crew_action import CrewAction
    from app.models.dial_config import DialConfig
    from app.models.poneglyph import Poneglyph
    from app.models.user import User
    from app.models.vivre_card import VivreCard


class Voyage(Base):
    __tablename__ = "voyages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), default=VoyageStatus.CHARTED.value, nullable=False
    )
    target_repo: Mapped[str | None] = mapped_column(String(500), nullable=True)
    phase_status: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="voyages")
    plans: Mapped[list[VoyagePlan]] = relationship(back_populates="voyage")
    poneglyphs: Mapped[list[Poneglyph]] = relationship(back_populates="voyage")
    vivre_cards: Mapped[list[VivreCard]] = relationship(back_populates="voyage")
    crew_actions: Mapped[list[CrewAction]] = relationship(back_populates="voyage")
    dial_config: Mapped[DialConfig | None] = relationship(back_populates="voyage")


class VoyagePlan(Base):
    __tablename__ = "voyage_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    voyage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voyages.id"), index=True, nullable=False
    )
    phases: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[str] = mapped_column(String(50), default="captain", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    voyage: Mapped[Voyage] = relationship(back_populates="plans")
