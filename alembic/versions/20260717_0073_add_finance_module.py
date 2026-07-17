"""Finance module: own infrastructure P&L, независимый от панельного infra-billing.

Revision ID: 0073
Revises: 0072
Create Date: 2026-07-17

Таблицы:
- finance_categories — категории расходов/доходов (системные + свои)
- finance_providers  — провайдеры (хостеры, рекламные площадки...)
- finance_items      — регулярные/разовые записи с валютой и циклом оплаты
- finance_payments   — история платежей с фиксацией курса к RUB на момент оплаты
- finance_rates      — курсы валют к RUB (авто из ЦБ РФ + ручные)
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0073"
down_revision: Union[str, None] = "0072"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS finance_categories (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'expense',
            color TEXT,
            icon TEXT,
            is_system BOOLEAN NOT NULL DEFAULT false,
            sort_order INT NOT NULL DEFAULT 100,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE (name, kind)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS finance_providers (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            url TEXT,
            favicon_url TEXT,
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS finance_items (
            id SERIAL PRIMARY KEY,
            kind TEXT NOT NULL DEFAULT 'expense',
            name TEXT NOT NULL,
            category_id INT REFERENCES finance_categories(id) ON DELETE SET NULL,
            provider_id INT REFERENCES finance_providers(id) ON DELETE SET NULL,
            node_uuid UUID,
            currency TEXT NOT NULL DEFAULT 'RUB',
            amount NUMERIC(14,2) NOT NULL DEFAULT 0,
            billing_cycle TEXT NOT NULL DEFAULT 'monthly',
            cycle_days INT,
            next_due_at DATE,
            url TEXT,
            notes TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            last_reminded_at DATE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_finance_items_due ON finance_items (status, next_due_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_finance_items_node ON finance_items (node_uuid) WHERE node_uuid IS NOT NULL")

    # item_id SET NULL + снапшот item_name/kind: история платежей переживает удаление записи
    op.execute("""
        CREATE TABLE IF NOT EXISTS finance_payments (
            id SERIAL PRIMARY KEY,
            item_id INT REFERENCES finance_items(id) ON DELETE SET NULL,
            item_name TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'expense',
            paid_at DATE NOT NULL,
            amount NUMERIC(14,2) NOT NULL,
            currency TEXT NOT NULL,
            rate_rub NUMERIC(18,8),
            comment TEXT,
            source TEXT NOT NULL DEFAULT 'manual',
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_finance_payments_paid_at ON finance_payments (paid_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_finance_payments_item ON finance_payments (item_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS finance_rates (
            currency TEXT PRIMARY KEY,
            rate_rub NUMERIC(18,8) NOT NULL,
            is_manual BOOLEAN NOT NULL DEFAULT false,
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("INSERT INTO finance_rates (currency, rate_rub, is_manual) VALUES ('RUB', 1, true) ON CONFLICT (currency) DO NOTHING")

    # Системные категории
    op.execute("""
        INSERT INTO finance_categories (name, kind, color, icon, is_system, sort_order) VALUES
            ('Ноды', 'expense', '#06b6d4', '🖥️', true, 10),
            ('Админ-серверы', 'expense', '#8b5cf6', '🔒', true, 20),
            ('Домены', 'expense', '#f59e0b', '🌐', true, 30),
            ('Реклама', 'expense', '#ef4444', '📣', true, 40),
            ('Личные проекты', 'expense', '#10b981', '🧪', true, 50),
            ('Прочее', 'expense', '#64748b', '📦', true, 90),
            ('Подписки', 'income', '#10b981', '💳', true, 10),
            ('Прочее', 'income', '#64748b', '💰', true, 90)
        ON CONFLICT (name, kind) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS finance_payments")
    op.execute("DROP TABLE IF EXISTS finance_items")
    op.execute("DROP TABLE IF EXISTS finance_providers")
    op.execute("DROP TABLE IF EXISTS finance_categories")
    op.execute("DROP TABLE IF EXISTS finance_rates")
