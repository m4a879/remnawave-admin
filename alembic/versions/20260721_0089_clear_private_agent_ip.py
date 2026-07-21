"""Чистка приватных agent_ip у нод.

Когда коллектор-батчи заходили через внутренний прокси (nginx в docker-сети),
в nodes.agent_ip записывался приватный адрес прокси (один и тот же 172.x у
всех нод) — BS-Check и матчинг финмодуля работали по мусорному IP. Код больше
приватные адреса не записывает; эта миграция вычищает уже записанные —
следующий батч агента заполнит колонку настоящим публичным IP.

Revision ID: 0089
Revises: 0088
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0089"
down_revision: Union[str, None] = "0088"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# RFC1918 + loopback + link-local + IPv6 ULA/loopback
_PRIVATE_RE = (
    r"^(10\.|172\.(1[6-9]|2[0-9]|3[01])\.|192\.168\.|127\.|169\.254\.|"
    r"[fF][cCdD]|::1$)"
)


def upgrade() -> None:
    op.execute(
        f"UPDATE nodes SET agent_ip = NULL "
        f"WHERE agent_ip IS NOT NULL AND agent_ip ~ '{_PRIVATE_RE}'"
    )


def downgrade() -> None:
    pass  # данные восстановит следующий батч агента
