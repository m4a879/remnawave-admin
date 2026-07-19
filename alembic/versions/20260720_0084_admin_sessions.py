"""Активные сессии админов — список входов + отзыв.

Revision ID: 0084
Revises: 0083
Create Date: 2026-07-20

Каждый успешный вход account-backed админа создаёт строку сессии (id = sid,
зашитый в access/refresh JWT). Отзыв = revoked_at; refresh проверяет строку
как источник истины, get_current_admin — быстрый in-memory-кэш отзыва.
Легаси env-админы (без account_id) не трекаются — sid в токен не пишется.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0084"
down_revision: Union[str, None] = "0083"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS admin_sessions (
            id TEXT PRIMARY KEY,
            account_id INTEGER NOT NULL,
            auth_method TEXT NOT NULL DEFAULT 'password',
            ip TEXT,
            user_agent TEXT,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            last_seen_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
            revoked_at TIMESTAMP WITH TIME ZONE
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_admin_sessions_account "
        "ON admin_sessions (account_id) WHERE revoked_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS admin_sessions")
