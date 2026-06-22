"""log book entries

Revision ID: e5f6a1b2c3d4
Revises: d4e5f6a1b2c3
Create Date: 2026-06-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e5f6a1b2c3d4"
down_revision: str | None = "d4e5f6a1b2c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "log_book_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("repo", sa.String(length=500), nullable=False),
        sa.Column(
            "voyage_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("voyages.id"),
            nullable=True,
        ),
        sa.Column("author", sa.String(length=50), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_log_book_entries_repo", "log_book_entries", ["repo"])
    op.create_index(
        "ix_log_book_entries_repo_created",
        "log_book_entries",
        ["repo", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_log_book_entries_repo_created", table_name="log_book_entries")
    op.drop_index("ix_log_book_entries_repo", table_name="log_book_entries")
    op.drop_table("log_book_entries")
