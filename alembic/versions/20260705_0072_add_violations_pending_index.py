"""Add partial index on violations for pending (unresolved) rows.

Revision ID: 0072
Revises: 0071
Create Date: 2026-07-05

Частый горячий фильтр `WHERE action_taken IS NULL` (виджет «открытые
нарушения» на дашборде, annul-all) шёл seq scan — индекса на action_taken
не было. Частичный индекс покрывает только pending-строки (обычно малая
доля таблицы), поэтому компактен и ускоряет и COUNT(*), и
GROUP BY recommended_action по нерассмотренным нарушениям.

CONCURRENTLY — чтобы не блокировать запись в violations на проде.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0072"
down_revision: Union[str, None] = "0071"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # CONCURRENTLY нельзя внутри транзакции — выходим в autocommit
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_violations_pending "
            "ON violations (detected_at DESC) WHERE action_taken IS NULL"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_violations_pending")
