"""БС-проверки нод (bschekbot) — история результатов probe.

Revision ID: 0079
Revises: 0078
Create Date: 2026-07-19

Хранит результат проверки IP ноды через операторов РФ: passed/total + полный
ответ probe в JSONB. Индекс по (node_uuid, checked_at) — для последнего/истории.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0079"
down_revision: Union[str, None] = "0078"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS node_bscheck (
            id SERIAL PRIMARY KEY,
            node_uuid TEXT NOT NULL,
            checked_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            passed INTEGER NOT NULL DEFAULT 0,
            total INTEGER NOT NULL DEFAULT 0,
            cost_credits INTEGER,
            result JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_by TEXT
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_node_bscheck_node "
        "ON node_bscheck (node_uuid, checked_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS node_bscheck")
