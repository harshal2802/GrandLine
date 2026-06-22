"""LogBookEntry — the Log Book: per-repo memory that persists across voyages.

In One Piece a ship's Log Book is the durable record of everything learned on
past voyages. Here it is a per-repo knowledge store keyed on
``Voyage.target_repo`` so the Captain can recall a repository's layout,
conventions, decisions, and gotchas when charting a new course — the crew never
re-learns the same stack twice. Unlike Vivre Cards (which checkpoint state WITHIN
a voyage), Log Book entries persist ACROSS voyages.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class LogBookEntry(Base):
    """A single piece of prior knowledge recorded for a repository."""

    __tablename__ = "log_book_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Per-repo key — matches ``Voyage.target_repo``. Indexed for recall lookups.
    repo: Mapped[str] = mapped_column(String(500), index=True, nullable=False)
    # The voyage that produced this learning, if any (repo-scoped entries may
    # have no originating voyage).
    voyage_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voyages.id"), nullable=True
    )
    # Crew role string (e.g. "captain") or "user".
    author: Mapped[str] = mapped_column(String(50), nullable=False)
    # Locked taxonomy: convention | decision | layout | gotcha | summary.
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # Composite index for most-recent-first recall scoped to a repo.
        Index("ix_log_book_entries_repo_created", "repo", "created_at"),
    )
