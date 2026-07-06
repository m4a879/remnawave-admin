"""Add partial index on violations for pending (unresolved) rows.

Revision ID: 0072
Revises: 0071
Create Date: 2026-07-05

Частый горячий фильтр `WHERE action_taken IS NULL` (виджет «открытые
нарушения» на дашборде, annul-all) шёл seq scan — индекса на action_taken
не было. Частичный индекс покрывает только pending-строки (обычно малая
доля таблицы), поэтому компактен и ускоряет и COUNT(*), и
GROUP BY recommended_action по нерассмотренным нарушениям.

Без CONCURRENTLY (как и 0043): main.py запускает upgrade на соединении,
где уже были statements (детач плагин-ревизий) — SQLAlchemy автобегином
открывает транзакцию, alembic считает её внешней, и autocommit_block()
падает на assert. Обычный CREATE INDEX держит SHARE-блокировку только на
время построения частичного индекса; миграция идёт на старте, когда
коллектор — единственный писатель violations — ещё не поднят.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0072"
down_revision: Union[str, None] = "0071"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_violations_pending "
        "ON violations (detected_at DESC) WHERE action_taken IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_violations_pending")
