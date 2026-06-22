from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class BrowserCheck(Base):
    """A persisted Bedside Browser run (Phase 23).

    Records the outcome of driving a headless browser against a running app —
    "tests pass AND the page renders". The ``screenshot_ref`` is the opaque ref
    the Ship's Log surfaces (via a ``BROWSER_CHECK_RUN`` CrewAction).
    """

    __tablename__ = "browser_checks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    voyage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voyages.id"), index=True, nullable=False
    )
    phase_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    passed: Mapped[bool] = mapped_column(nullable=False)
    screenshot_ref: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    console_errors: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    failed_assertions: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
