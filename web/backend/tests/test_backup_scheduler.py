"""Tests for scheduled auto-backup logic (_run_auto_backup_if_due)."""
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

import web.backend.core.backup_service as bs


def _fake_config(values):
    m = MagicMock()
    m.get.side_effect = lambda k, d=None: values.get(k, d)
    return m


def _now_hhmm():
    return datetime.now(timezone.utc).strftime("%H:%M")


@pytest.fixture(autouse=True)
def _reset_state():
    bs._last_auto_backup_ts = None
    yield
    bs._last_auto_backup_ts = None


class TestAutoBackupDue:
    @pytest.mark.asyncio
    async def test_disabled_does_nothing(self):
        cfg = _fake_config({"backup_auto_enabled": False})
        with patch("shared.config_service.config_service", cfg), \
                patch.object(bs, "create_database_backup", new_callable=AsyncMock) as mk:
            await bs._run_auto_backup_if_due()
            mk.assert_not_called()

    @pytest.mark.asyncio
    async def test_wrong_time_does_nothing(self):
        # Daily mode, schedule time that can never match "HH:MM"
        cfg = _fake_config({
            "backup_auto_enabled": True, "backup_auto_time": "99:99",
            "backup_auto_interval_hours": 0,
        })
        with patch("shared.config_service.config_service", cfg), \
                patch.object(bs, "create_database_backup", new_callable=AsyncMock) as mk:
            await bs._run_auto_backup_if_due()
            mk.assert_not_called()

    @pytest.mark.asyncio
    async def test_daily_due_creates_db_only(self):
        cfg = _fake_config({
            "backup_auto_enabled": True, "backup_auto_time": _now_hhmm(),
            "backup_auto_interval_hours": 0, "backup_auto_telegram": False,
            "backup_auto_config": False, "backup_auto_keep_count": 10,
            "backup_auto_keep_days": 30,
        })
        with patch("shared.config_service.config_service", cfg), \
                patch.dict("os.environ", {"DATABASE_URL": "postgres://x"}), \
                patch.object(bs, "create_database_backup", new_callable=AsyncMock,
                             return_value={"filename": "db.sql.gz", "size_bytes": 1}) as mk_db, \
                patch.object(bs, "export_config", new_callable=AsyncMock) as mk_cfg, \
                patch.object(bs, "rotate_backups", return_value=0), \
                patch.object(bs, "_log_and_maybe_send", new_callable=AsyncMock):
            await bs._run_auto_backup_if_due()
            mk_db.assert_awaited_once()
            mk_cfg.assert_not_called()  # config backup disabled

    @pytest.mark.asyncio
    async def test_config_backup_when_enabled(self):
        cfg = _fake_config({
            "backup_auto_enabled": True, "backup_auto_time": _now_hhmm(),
            "backup_auto_interval_hours": 0, "backup_auto_config": True,
            "backup_auto_telegram": False, "backup_auto_keep_count": 10,
            "backup_auto_keep_days": 30,
        })
        with patch("shared.config_service.config_service", cfg), \
                patch.dict("os.environ", {"DATABASE_URL": "postgres://x"}), \
                patch.object(bs, "create_database_backup", new_callable=AsyncMock,
                             return_value={"filename": "db.sql.gz", "size_bytes": 1}), \
                patch.object(bs, "export_config", new_callable=AsyncMock,
                             return_value={"filename": "cfg.json", "size_bytes": 1}) as mk_cfg, \
                patch.object(bs, "rotate_backups", return_value=0), \
                patch.object(bs, "_log_and_maybe_send", new_callable=AsyncMock):
            await bs._run_auto_backup_if_due()
            mk_cfg.assert_awaited_once()  # config backup enabled

    @pytest.mark.asyncio
    async def test_daily_not_twice_same_day(self):
        bs._last_auto_backup_ts = datetime.now(timezone.utc)  # already ran today
        cfg = _fake_config({
            "backup_auto_enabled": True, "backup_auto_time": _now_hhmm(),
            "backup_auto_interval_hours": 0,
        })
        with patch("shared.config_service.config_service", cfg), \
                patch.object(bs, "create_database_backup", new_callable=AsyncMock) as mk:
            await bs._run_auto_backup_if_due()
            mk.assert_not_called()

    @pytest.mark.asyncio
    async def test_interval_due_after_n_hours(self):
        # interval 4h, last run 5h ago → due regardless of current clock time
        bs._last_auto_backup_ts = datetime.now(timezone.utc) - timedelta(hours=5)
        cfg = _fake_config({
            "backup_auto_enabled": True, "backup_auto_time": "00:00",
            "backup_auto_interval_hours": 4, "backup_auto_telegram": False,
            "backup_auto_config": False, "backup_auto_keep_count": 10,
            "backup_auto_keep_days": 30,
        })
        with patch("shared.config_service.config_service", cfg), \
                patch.dict("os.environ", {"DATABASE_URL": "postgres://x"}), \
                patch.object(bs, "create_database_backup", new_callable=AsyncMock,
                             return_value={"filename": "db.sql.gz", "size_bytes": 1}) as mk_db, \
                patch.object(bs, "rotate_backups", return_value=0), \
                patch.object(bs, "_log_and_maybe_send", new_callable=AsyncMock):
            await bs._run_auto_backup_if_due()
            mk_db.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_interval_not_due_yet(self):
        # interval 4h, last run 1h ago → not due
        bs._last_auto_backup_ts = datetime.now(timezone.utc) - timedelta(hours=1)
        cfg = _fake_config({
            "backup_auto_enabled": True, "backup_auto_time": "00:00",
            "backup_auto_interval_hours": 4,
        })
        with patch("shared.config_service.config_service", cfg), \
                patch.object(bs, "create_database_backup", new_callable=AsyncMock) as mk:
            await bs._run_auto_backup_if_due()
            mk.assert_not_called()
