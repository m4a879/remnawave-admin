"""OAuth2 SSO — привязки внешних аккаунтов (Google/GitHub) к админам.

Revision ID: 0083
Revises: 0082
Create Date: 2026-07-20

Вход по OAuth работает ТОЛЬКО если внешняя личность (provider, external_id)
привязана к существующему admin_accounts.id — авто-создания нет (безопасность).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0083"
down_revision: Union[str, None] = "0082"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS oauth_links (
            id SERIAL PRIMARY KEY,
            account_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            external_id TEXT NOT NULL,
            email TEXT,
            name TEXT,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            last_used_at TIMESTAMP WITH TIME ZONE,
            UNIQUE (provider, external_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_oauth_links_account ON oauth_links (account_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS oauth_links")
