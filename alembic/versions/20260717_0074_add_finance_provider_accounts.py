"""Finance phase 2: API-подключения хостеров + дневные снапшоты балансов.

Revision ID: 0074
Revises: 0073
Create Date: 2026-07-17

Таблицы:
- finance_provider_accounts — подключение к клиентскому API хостера
  (адаптер, шифрованные креды, статус синка, последний баланс)
- finance_balance_snapshots  — баланс аккаунта по дням для тренда
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0074"
down_revision: Union[str, None] = "0073"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # credentials — Fernet-шифрованный JSON (web.backend.core.crypto),
    # один аккаунт на провайдера: кнопка «Подключить API» на карточке
    op.execute("""
        CREATE TABLE IF NOT EXISTS finance_provider_accounts (
            id SERIAL PRIMARY KEY,
            provider_id INT NOT NULL UNIQUE REFERENCES finance_providers(id) ON DELETE CASCADE,
            adapter TEXT NOT NULL,
            base_url TEXT,
            credentials TEXT NOT NULL,
            auto_sync BOOLEAN NOT NULL DEFAULT true,
            low_balance_threshold NUMERIC(14,2),
            balance NUMERIC(14,2),
            balance_currency TEXT,
            services JSONB,
            last_sync_at TIMESTAMP,
            last_sync_status TEXT,
            last_sync_error TEXT,
            last_alerted_at DATE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS finance_balance_snapshots (
            id SERIAL PRIMARY KEY,
            account_id INT NOT NULL REFERENCES finance_provider_accounts(id) ON DELETE CASCADE,
            snapshot_date DATE NOT NULL,
            balance NUMERIC(14,2) NOT NULL,
            currency TEXT NOT NULL,
            UNIQUE (account_id, snapshot_date)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_finance_snapshots_date"
        " ON finance_balance_snapshots (snapshot_date)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS finance_balance_snapshots")
    op.execute("DROP TABLE IF EXISTS finance_provider_accounts")
