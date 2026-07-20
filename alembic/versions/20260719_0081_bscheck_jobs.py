"""BS-Check: сохранённые авто-тесты (jobs) с индивидуальным расписанием.

Revision ID: 0081
Revises: 0080
Create Date: 2026-07-19

Именованные тесты: kind (node|probe|scan|vless) + config (цели/операторы/…) +
свой интервал/бюджет/алерт. node_bscheck получает job_id — привязка результата
к тесту (история и бюджет по каждому job).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0081"
down_revision: Union[str, None] = "0080"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS bscheck_jobs (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT true,
            interval_minutes INTEGER NOT NULL DEFAULT 360,
            config JSONB NOT NULL DEFAULT '{}'::jsonb,
            budget_daily INTEGER NOT NULL DEFAULT 0,
            alert BOOLEAN NOT NULL DEFAULT true,
            last_run_at TIMESTAMP WITH TIME ZONE,
            created_by TEXT,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("ALTER TABLE node_bscheck ADD COLUMN IF NOT EXISTS job_id INTEGER")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_node_bscheck_job "
        "ON node_bscheck (job_id, checked_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_node_bscheck_job")
    op.execute("ALTER TABLE node_bscheck DROP COLUMN IF EXISTS job_id")
    op.execute("DROP TABLE IF EXISTS bscheck_jobs")
