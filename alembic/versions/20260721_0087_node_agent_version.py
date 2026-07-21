"""Версия node-agent на ноде — для подсказки «пора обновить агент».

Revision ID: 0087
Revises: 0086
Create Date: 2026-07-21

Агент репортит свою версию в каждом батче коллектора; панель сравнивает
с эталоном (shared/agent_version.py) и показывает бейдж обновления.
NULL = агент старый и версию ещё не репортил (до 1.1.0) либо не установлен.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0087"
down_revision: Union[str, None] = "0086"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE nodes ADD COLUMN IF NOT EXISTS agent_version TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE nodes DROP COLUMN IF EXISTS agent_version")
