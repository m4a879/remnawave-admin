"""Passkeys / WebAuthn — учётные данные (credentials) админов.

Revision ID: 0082
Revises: 0081
Create Date: 2026-07-20

Хранит публичный ключ passkey, счётчик подписей и метаданные. Привязка к
admin_accounts.id. credential_id/public_key — base64url.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0082"
down_revision: Union[str, None] = "0081"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS webauthn_credentials (
            id SERIAL PRIMARY KEY,
            account_id INTEGER NOT NULL,
            credential_id TEXT NOT NULL UNIQUE,
            public_key TEXT NOT NULL,
            sign_count BIGINT NOT NULL DEFAULT 0,
            transports TEXT,
            name TEXT,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            last_used_at TIMESTAMP WITH TIME ZONE
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_webauthn_account ON webauthn_credentials (account_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS webauthn_credentials")
