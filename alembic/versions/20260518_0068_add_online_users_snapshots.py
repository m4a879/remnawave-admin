"""Add online_users_snapshots table for users-online trend chart.

Revision ID: 0068
Revises: 0067
Create Date: 2026-05-18

Stores cluster-wide users-online count at each recorder tick (~5 min),
enabling avg/max trend aggregation on Analytics' Trends tab.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0068"
down_revision: Union[str, None] = "0067"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS online_users_snapshots (
            id BIGSERIAL PRIMARY KEY,
            ts TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            total INTEGER NOT NULL DEFAULT 0
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_online_users_snapshots_ts
        ON online_users_snapshots (ts DESC)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS online_users_snapshots")
