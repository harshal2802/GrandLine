"""browser checks (Bedside Browser — Phase 23)

Adds the ``browser_checks`` table — a persisted record of a Doctor Bedside
Browser run (driving a headless browser against a running app and asserting the
page renders). The ``screenshot_ref`` is the opaque ref the Ship's Log surfaces.

Revision ID: b8d4f2a6c1e3
Revises: a7c9e1f3b5d2
Create Date: 2026-06-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b8d4f2a6c1e3"
down_revision: str | None = "a7c9e1f3b5d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "browser_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "voyage_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("voyages.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("phase_number", sa.Integer(), nullable=True),
        sa.Column("url", sa.String(2000), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("screenshot_ref", sa.String(2000), nullable=True),
        sa.Column(
            "console_errors",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "failed_assertions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("browser_checks")
