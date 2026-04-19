"""deployments

Revision ID: c3d4e5f6a1b2
Revises: b2c3d4e5f6a1
Create Date: 2026-04-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c3d4e5f6a1b2"
down_revision: str | None = "b2c3d4e5f6a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "deployments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "voyage_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("voyages.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("tier", sa.String(20), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("git_ref", sa.String(255), nullable=False),
        sa.Column("git_sha", sa.String(64), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("url", sa.String(500), nullable=True),
        sa.Column("backend_log", sa.Text(), nullable=True),
        sa.Column("diagnosis", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "previous_deployment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("deployments.id"),
            nullable=True,
            index=True,
        ),
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
    )
    op.create_index(
        "ix_deployments_voyage_tier_created",
        "deployments",
        ["voyage_id", "tier", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_deployments_voyage_tier_created", table_name="deployments")
    op.drop_table("deployments")
