"""Доменный лимит отправки: 0 = наследовать глобальный mailserver_max_send_per_hour.

Revision ID: 0086
Revises: 0085
Create Date: 2026-07-20

Раньше domain_config.max_send_per_hour стоял DEFAULT 100 и был единственным
местом, где реально применялся почасовой лимит домена, — но в UI его редактировать
было негде, а глобальная настройка mailserver_max_send_per_hour ни на что не влияла
(её не читал ни один участок кода). Из-за этого поднятие глобального лимита в
настройках не давало эффекта, и домены молча упирались в дефолтные 100 писем/час.

Новая семантика: 0 (или NULL) в строке домена = наследовать глобальный лимит;
любое положительное значение = явный override per-domain. Существующие строки со
старым дефолтом 100 переводим в 0 (наследование), чтобы глобальная настройка
наконец заработала. Явно выставленные не-100 значения не трогаем.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0086"
down_revision: Union[str, None] = "0085"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE domain_config ALTER COLUMN max_send_per_hour SET DEFAULT 0")
    # Старый дефолт 100 → 0 (наследовать глобальный). Осознанные override не трогаем.
    op.execute("UPDATE domain_config SET max_send_per_hour = 0 WHERE max_send_per_hour = 100")


def downgrade() -> None:
    op.execute("UPDATE domain_config SET max_send_per_hour = 100 WHERE max_send_per_hour = 0")
    op.execute("ALTER TABLE domain_config ALTER COLUMN max_send_per_hour SET DEFAULT 100")
