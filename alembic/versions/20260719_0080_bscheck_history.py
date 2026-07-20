"""BS-Check: единый журнал проверок (ноды/IP/скан/vless).

Revision ID: 0080
Revises: 0079
Create Date: 2026-07-19

Расширяет node_bscheck до универсального лога: kind (node|probe|scan|vless),
target (IP/CIDR/метка), node_uuid становится nullable (у ad-hoc проверок ноды нет).
Индекс по checked_at DESC — для вкладки «История».
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0080"
down_revision: Union[str, None] = "0079"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE node_bscheck ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'node'")
    op.execute("ALTER TABLE node_bscheck ADD COLUMN IF NOT EXISTS target TEXT")
    op.execute("ALTER TABLE node_bscheck ALTER COLUMN node_uuid DROP NOT NULL")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_node_bscheck_checked "
        "ON node_bscheck (checked_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_node_bscheck_checked")
    op.execute("ALTER TABLE node_bscheck DROP COLUMN IF EXISTS target")
    op.execute("ALTER TABLE node_bscheck DROP COLUMN IF EXISTS kind")
    # node_uuid NOT NULL не восстанавливаем — в таблице могут быть ad-hoc строки с NULL
