"""Add watchlist alert fields: alert_channel, dedup_window, last_hit, hit_count.

Revision ID: 002
Revises: 001
Create Date: 2026-05-27
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add watchlist alert tracking fields."""
    op.add_column(
        "watchlists",
        sa.Column(
            "alert_channel",
            sa.String(50),
            nullable=False,
            server_default="webhook",
            comment="Alert delivery channel: webhook, email, sms",
        ),
    )
    op.add_column(
        "watchlists",
        sa.Column(
            "dedup_window",
            sa.Integer(),
            nullable=False,
            server_default="300",
            comment="Deduplication window in seconds",
        ),
    )
    op.add_column(
        "watchlists",
        sa.Column(
            "last_hit",
            sa.DateTime(),
            nullable=True,
            comment="Last time watchlist pattern matched",
        ),
    )
    op.add_column(
        "watchlists",
        sa.Column(
            "hit_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Number of times pattern matched in session",
        ),
    )


def downgrade() -> None:
    """Remove watchlist alert fields."""
    op.drop_column("watchlists", "hit_count")
    op.drop_column("watchlists", "last_hit")
    op.drop_column("watchlists", "dedup_window")
    op.drop_column("watchlists", "alert_channel")
