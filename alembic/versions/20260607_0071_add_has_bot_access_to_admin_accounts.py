"""Add has_bot_access column to admin_accounts for Telegram bot RBAC.

Revision ID: 0071
Revises: 0070
Create Date: 2026-06-07

Adds a boolean flag to opt admins into Telegram bot access.
Only admins with has_bot_access=true AND a telegram_id set
will be granted role-based access to the bot.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0071"
down_revision: Union[str, None] = "0070"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE admin_accounts
        ADD COLUMN IF NOT EXISTS has_bot_access BOOLEAN
        NOT NULL DEFAULT false
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE admin_accounts DROP COLUMN IF EXISTS has_bot_access")
