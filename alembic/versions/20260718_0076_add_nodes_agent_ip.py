"""Публичный IP ноды по коллектор-батчам (nodes.agent_ip).

Revision ID: 0076
Revises: 0075
Create Date: 2026-07-18

За оверлеем (NetBird и т.п.) nodes.address — туннельный адрес, а хостерские
API отдают публичные IP. Коллектор видит реальный source-IP агентских батчей —
храним его для сопоставления серверов хостеров с нодами в финмодуле.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0076"
down_revision: Union[str, None] = "0075"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE nodes ADD COLUMN IF NOT EXISTS agent_ip VARCHAR(64)")


def downgrade() -> None:
    op.execute("ALTER TABLE nodes DROP COLUMN IF EXISTS agent_ip")
