"""StandingOrder — reusable voyage templates / presets.

In One Piece a captain leaves Standing Orders: durable instructions the crew
follows without being briefed afresh each time. Here a Standing Order is a named,
reusable bundle of ``{dial config + optional plan skeleton + injected context +
default target repo}`` owned by a user. Charting *from* a Standing Order applies
the preset's dial config (instead of the per-voyage default) and its repo/context
defaults, so recurring task shapes — "bugfix voyage", "dep-bump voyage" — chart
in one call.

Standing Orders are per-user presets, not per-voyage state: they are owned by
``user_id``, name-unique per owner, and never shared across users. Charting from
one produces an ordinary Voyage — the preset is a stamp, not a live link.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class StandingOrder(Base):
    """A named, reusable bundle of voyage configuration owned by a user."""

    __tablename__ = "standing_orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Owner — Standing Orders are per-user presets, never shared across users.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Default repo for voyages charted from this order (matches Voyage.target_repo).
    target_repo: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # A ``{role_mapping, fallback_chain}`` bundle applied to the charted voyage's
    # DialConfig in place of the deployment default.
    dial_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # Optional pre-seeded plan phases (opaque JSONB in this phase).
    plan_skeleton: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # Framing prepended to the planning task / voyage description on chart.
    injected_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        # A Standing Order's name is unambiguous per owner.
        UniqueConstraint("user_id", "name", name="uq_standing_orders_user_name"),
    )
