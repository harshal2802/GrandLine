"""health_checks

Revision ID: a1b2c3d4e5f6
Revises: 00b24ef2f7d8
Create Date: 2026-04-16

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "00b24ef2f7d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "health_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "voyage_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("voyages.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "poneglyph_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("poneglyphs.id"),
            nullable=True,
            index=True,
        ),
        sa.Column("phase_number", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("framework", sa.String(20), nullable=False, server_default="pytest"),
        sa.Column("last_run_status", sa.String(20), nullable=True),
        sa.Column("last_run_output", sa.Text(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_by", sa.String(50), nullable=False, server_default="doctor"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("health_checks")
