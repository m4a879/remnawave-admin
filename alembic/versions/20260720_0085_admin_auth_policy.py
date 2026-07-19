"""Политика метода входа на админа — какими способами он может логиниться.

Revision ID: 0085
Revises: 0084
Create Date: 2026-07-20

admin_accounts.allowed_auth_methods — JSON-массив разрешённых способов
(password/telegram/passkey/oauth). NULL или пусто = все разрешены (дефолт,
обратная совместимость). Проверяется на входе для account-backed админов.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0085"
down_revision: Union[str, None] = "0084"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE admin_accounts ADD COLUMN IF NOT EXISTS allowed_auth_methods TEXT"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE admin_accounts DROP COLUMN IF EXISTS allowed_auth_methods")
