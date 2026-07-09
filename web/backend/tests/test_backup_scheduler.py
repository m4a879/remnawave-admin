"""Tests for scheduled auto-backup logic (_run_auto_backup_if_due)."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

import web.backend.core.backup_service as bs


def _fake_config(values):
    m = MagicMock()
    m.get.side_effect = lambda k, d=None: values.get(k, d)
    return m


def _patch_now(hhmm, date="2026-07-09"):
    """Patch backup_service.datetime so now().strftime returns fixed values."""
    dt = patch.object(bs, "datetime")
    mock = dt.start()
    mock.now.return_value.strftime.side_effect = (
        lambda fmt: hhmm if fmt == "%H:%M" else date
    )
    return dt


@pytest.fixture(autouse=True)
def _reset_state():
    bs._last_auto_backup_date = None
    yield
    bs._last_auto_backup_date = None


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
        cfg = _fake_config({"backup_auto_enabled": True, "backup_auto_time": "03:00"})
        dt = _patch_now("12:00")
        try:
            with patch("shared.config_service.config_service", cfg), \
                    patch.object(bs, "create_database_backup", new_callable=AsyncMock) as mk:
                await bs._run_auto_backup_if_due()
                mk.assert_not_called()
        finally:
            dt.stop()

    @pytest.mark.asyncio
    async def test_due_creates_backup_and_rotates(self):
        cfg = _fake_config({
            "backup_auto_enabled": True,
            "backup_auto_time": "03:00",
            "backup_auto_telegram": False,
            "backup_auto_keep_count": 10,
            "backup_auto_keep_days": 30,
        })
        dt = _patch_now("03:00")
        try:
            with patch("shared.config_service.config_service", cfg), \
                    patch.dict("os.environ", {"DATABASE_URL": "postgres://x"}), \
                    patch.object(bs, "create_database_backup", new_callable=AsyncMock,
                                 return_value={"filename": "db_backup_x.sql.gz", "size_bytes": 123}) as mk_create, \
                    patch.object(bs, "rotate_backups", return_value=0) as mk_rotate:
                await bs._run_auto_backup_if_due()
                mk_create.assert_awaited_once()
                mk_rotate.assert_called_once()
        finally:
            dt.stop()

    @pytest.mark.asyncio
    async def test_not_twice_same_day(self):
        bs._last_auto_backup_date = "2026-07-09"
        cfg = _fake_config({"backup_auto_enabled": True, "backup_auto_time": "03:00"})
        dt = _patch_now("03:00")
        try:
            with patch("shared.config_service.config_service", cfg), \
                    patch.object(bs, "create_database_backup", new_callable=AsyncMock) as mk:
                await bs._run_auto_backup_if_due()
                mk.assert_not_called()
        finally:
            dt.stop()
