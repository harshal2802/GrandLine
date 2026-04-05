"""initial_models

Revision ID: 00b24ef2f7d8
Revises:
Create Date: 2026-04-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "00b24ef2f7d8"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("username", sa.String(100), nullable=False, unique=True, index=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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

    # Voyages
    op.create_table(
        "voyages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="CHARTED"),
        sa.Column("target_repo", sa.String(500), nullable=True),
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

    # Voyage Plans
    op.create_table(
        "voyage_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "voyage_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("voyages.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("phases", postgresql.JSONB(), nullable=False),
        sa.Column("created_by", sa.String(50), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Poneglyphs (PDD prompts/artifacts)
    op.create_table(
        "poneglyphs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "voyage_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("voyages.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("phase_number", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_by", sa.String(50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Vivre Cards (state checkpoints)
    op.create_table(
        "vivre_cards",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "voyage_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("voyages.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("crew_member", sa.String(50), nullable=False),
        sa.Column("state_data", postgresql.JSONB(), nullable=False),
        sa.Column("checkpoint_reason", sa.String(50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Crew Actions (agent activity log)
    op.create_table(
        "crew_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "voyage_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("voyages.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("crew_member", sa.String(50), nullable=False, index=True),
        sa.Column("action_type", sa.String(100), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Dial Configs (LLM gateway config per voyage)
    op.create_table(
        "dial_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "voyage_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("voyages.id"),
            nullable=False,
            unique=True,
            index=True,
        ),
        sa.Column("role_mapping", postgresql.JSONB(), nullable=False),
        sa.Column("fallback_chain", postgresql.JSONB(), nullable=True),
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


def downgrade() -> None:
    op.drop_table("dial_configs")
    op.drop_table("crew_actions")
    op.drop_table("vivre_cards")
    op.drop_table("poneglyphs")
    op.drop_table("voyage_plans")
    op.drop_table("voyages")
    op.drop_table("users")
