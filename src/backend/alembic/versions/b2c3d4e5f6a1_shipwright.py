"""shipwright_runs and build_artifacts

Revision ID: b2c3d4e5f6a1
Revises: a1b2c3d4e5f6
Create Date: 2026-04-17

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b2c3d4e5f6a1"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shipwright_runs",
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
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("iteration_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("passed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_shipwright_runs_voyage_phase",
        "shipwright_runs",
        ["voyage_id", "phase_number"],
    )

    op.create_table(
        "build_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "voyage_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("voyages.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "shipwright_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shipwright_runs.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("phase_number", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("language", sa.String(20), nullable=False, server_default="python"),
        sa.Column("created_by", sa.String(50), nullable=False, server_default="shipwright"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_build_artifacts_voyage_phase",
        "build_artifacts",
        ["voyage_id", "phase_number"],
    )


def downgrade() -> None:
    op.drop_index("ix_build_artifacts_voyage_phase", table_name="build_artifacts")
    op.drop_table("build_artifacts")
    op.drop_index("ix_shipwright_runs_voyage_phase", table_name="shipwright_runs")
    op.drop_table("shipwright_runs")
