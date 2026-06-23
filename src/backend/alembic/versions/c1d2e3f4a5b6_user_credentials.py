"""user credentials (Sea Chest — Phase 0a)

Adds the ``user_credentials`` table — the encrypted per-user credential vault.
Each row stores ONLY the encrypted secret (``ciphertext`` BYTEA) plus non-secret
metadata (``kind``, ``label``, timestamps). There is NEVER a plaintext secret
column. Unique ``(user_id, kind)`` so a user has at most one credential per kind.

Revision ID: c1d2e3f4a5b6
Revises: b8d4f2a6c1e3
Create Date: 2026-06-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: str | None = "b8d4f2a6c1e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        # The encrypted secret — NEVER plaintext.
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "kind", name="uq_user_credentials_user_kind"),
    )


def downgrade() -> None:
    op.drop_table("user_credentials")
