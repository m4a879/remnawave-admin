"""Add admin-scoped user access and per-admin unlimited traffic policy.

Revision ID: 0070
Revises: 0069
Create Date: 2026-05-31

Adds created_by_admin_id to users table for RBAC admin-scoped user access.
Adds unlimited_traffic_policy column to admin_accounts for per-admin
control over whether they can set unlimited traffic on users.
Adds unrestricted_user_access flag to admin_accounts for opt-in
coexistence with node/squad access-policy scoping.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0070"
down_revision: Union[str, None] = "0069"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS created_by_admin_id INTEGER
        REFERENCES admin_accounts(id) ON DELETE SET NULL
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_created_by_admin
        ON users (created_by_admin_id)
    """)

    op.execute("""
        ALTER TABLE admin_accounts
        ADD COLUMN IF NOT EXISTS unlimited_traffic_policy VARCHAR(20)
        NOT NULL DEFAULT 'allowed'
    """)

    op.execute("""
        ALTER TABLE admin_accounts
        ADD COLUMN IF NOT EXISTS unrestricted_user_access BOOLEAN
        NOT NULL DEFAULT true
    """)

    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'chk_unlimited_traffic_policy'
            ) THEN
                ALTER TABLE admin_accounts
                ADD CONSTRAINT chk_unlimited_traffic_policy
                CHECK (unlimited_traffic_policy IN ('allowed', 'disabled', 'enforced'));
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE admin_accounts DROP CONSTRAINT IF EXISTS chk_unlimited_traffic_policy")
    op.execute("ALTER TABLE admin_accounts DROP COLUMN IF EXISTS unlimited_traffic_policy")
    op.execute("ALTER TABLE admin_accounts DROP COLUMN IF EXISTS unrestricted_user_access")
    op.execute("DROP INDEX IF EXISTS idx_users_created_by_admin")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS created_by_admin_id")
