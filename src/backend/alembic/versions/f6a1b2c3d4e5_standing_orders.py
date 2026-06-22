"""standing orders

Revision ID: f6a1b2c3d4e5
Revises: e5f6a1b2c3d4
Create Date: 2026-06-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f6a1b2c3d4e5"
down_revision: str | None = "e5f6a1b2c3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "standing_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("target_repo", sa.String(length=500), nullable=True),
        sa.Column("dial_config", postgresql.JSONB, nullable=True),
        sa.Column("plan_skeleton", postgresql.JSONB, nullable=True),
        sa.Column("injected_context", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "name", name="uq_standing_orders_user_name"),
    )
    op.create_index("ix_standing_orders_user_id", "standing_orders", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_standing_orders_user_id", table_name="standing_orders")
    op.drop_table("standing_orders")
