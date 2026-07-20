"""Пресеты создания юзера — именованные наборы дефолтов.

Revision ID: 0078
Revises: 0077
Create Date: 2026-07-18

Поля пресета лежат в JSONB `data` (гибкий набор: трафик/стратегия/HWID-лимит/
сквады/тег/срок в днях/статус) — форма создания юзера предзаполняется из них.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0078"
down_revision: Union[str, None] = "0077"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_presets (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            data JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_by TEXT,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_presets")
