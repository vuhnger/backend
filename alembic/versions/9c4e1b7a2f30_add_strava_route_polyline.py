"""add strava route polyline

Adds the raw route geometry Strava already returns with every activity in the
list response — no extra API calls needed to populate it. Nullable, so the
column lands on existing rows without a table rewrite; those rows stay NULL
until a full re-sync (`POST /strava/refresh-data?full=true`) backfills them,
which is a prerequisite for /strava/heatmap returning anything.

Revision ID: 9c4e1b7a2f30
Revises: 56883c337dbe
Create Date: 2026-07-25 10:12:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '9c4e1b7a2f30'
down_revision: str | Sequence[str] | None = '56883c337dbe'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'strava_activities',
        sa.Column('summary_polyline', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('strava_activities', 'summary_polyline')
