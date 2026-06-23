"""UserCredential — a Sea Chest entry: one encrypted-at-rest secret per user+kind.

The Sea Chest (Phase 0a) is the per-user credential vault. Each row stores ONLY
the encrypted secret (``ciphertext``) plus non-secret metadata — there is NEVER a
plaintext secret column. A user has at most one credential per ``kind`` (enforced
by the unique ``(user_id, kind)`` constraint); connecting again replaces it.

Decryption happens INTERNALLY (``SeaChestService.reveal``) for the Cabin/adapters
in later phases — never over the API, which exposes status only.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    LargeBinary,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class UserCredential(Base):
    """A single encrypted credential owned by a user (e.g. Claude Code / GitHub)."""

    __tablename__ = "user_credentials"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Owner — credentials are per-user and never shared across users.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=False
    )
    # Allowed kinds: "claude_code" | "github". Validated at the schema boundary.
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # The encrypted secret — Fernet ciphertext bytes. NEVER the plaintext secret.
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    # A non-secret hint (e.g. "token …abcd" last-4, or "device-login"). Optional.
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    # Set whenever the secret is decrypted for an internal consumer (the Cabin/
    # adapters). Nullable: a freshly-stored credential has never been used.
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # One credential per kind per user — connecting again replaces it.
        UniqueConstraint("user_id", "kind", name="uq_user_credentials_user_kind"),
    )
