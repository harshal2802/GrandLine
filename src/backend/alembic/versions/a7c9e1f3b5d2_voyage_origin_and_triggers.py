"""voyage origin and triggers

Adds the ``origin`` JSONB column to ``voyages`` — the canonical record of how a
voyage was triggered (a Message in a Bottle). NULL for a manually charted voyage;
populated for an externally triggered one (e.g. a GitHub issue webhook).

Revision ID: a7c9e1f3b5d2
Revises: f6a1b2c3d4e5
Create Date: 2026-06-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a7c9e1f3b5d2"
down_revision: str | None = "f6a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "voyages",
        sa.Column("origin", postgresql.JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("voyages", "origin")
