"""История версий конфигов (профили/шаблоны/сниппеты) для встроенного редактора.

Revision ID: 0077
Revises: 0076
Create Date: 2026-07-18

Снапшот пишется при каждом сохранении через наш API; дедуп по content_hash,
ретенция — последние N версий на сущность (чистится при вставке).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0077"
down_revision: Union[str, None] = "0076"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS config_versions (
            id BIGSERIAL PRIMARY KEY,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            entity_name TEXT,
            content TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            created_by TEXT,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_config_versions_entity
        ON config_versions (entity_type, entity_id, created_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS config_versions")
