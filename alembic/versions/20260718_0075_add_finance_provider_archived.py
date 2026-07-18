"""Finance: флаг архива у провайдеров (неактивные хостеры уходят в таб «Архив»).

Revision ID: 0075
Revises: 0074
Create Date: 2026-07-18
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0075"
down_revision: Union[str, None] = "0074"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE finance_providers "
        "ADD COLUMN IF NOT EXISTS archived BOOLEAN NOT NULL DEFAULT FALSE"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE finance_providers DROP COLUMN IF EXISTS archived")
