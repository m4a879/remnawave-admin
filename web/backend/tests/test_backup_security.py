"""Security tests for backup endpoints (H7 path traversal + H8 restore gate).

H8: restore/import/upload выполняют произвольный SQL/читают файлы под
postgres-суперюзером — должны требовать роль superadmin, а не грантуемый
backups:create.
H7: filename не должен позволять выход за BACKUP_DIR.
"""
import pytest
from unittest.mock import patch, AsyncMock

SUPERADMIN_ONLY_POSTS = [
    ("/api/v2/backups/restore", {"filename": "backup.sql.gz"}),
    ("/api/v2/backups/import-config", {"filename": "config.json"}),
    ("/api/v2/backups/import-users", {"filename": "users.json"}),
    ("/api/v2/backups/import-full-config", {"filename": "full.json"}),
]

TRAVERSAL_NAMES = ["../../etc/passwd", "/etc/passwd", "..\\..\\secret", "sub/dir.json"]


class TestRestoreRequiresSuperadmin:
    """H8 — manager с backups:create больше не может restore/import."""

    @pytest.mark.parametrize("path,body", SUPERADMIN_ONLY_POSTS)
    @pytest.mark.asyncio
    async def test_manager_forbidden(self, manager_client, path, body):
        resp = await manager_client.post(path, json=body)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_upload_forbidden_for_manager(self, manager_client):
        resp = await manager_client.post(
            "/api/v2/backups/upload",
            files={"file": ("backup.sql.gz", b"data", "application/gzip")},
        )
        assert resp.status_code == 403


class TestBackupPathTraversal:
    """H7 — filename с обходом каталога отсекается схемой (422)."""

    @pytest.mark.parametrize("bad", TRAVERSAL_NAMES)
    @pytest.mark.asyncio
    async def test_restore_rejects_traversal(self, client, bad):
        resp = await client.post("/api/v2/backups/restore", json={"filename": bad})
        assert resp.status_code == 422

    @pytest.mark.parametrize("bad", TRAVERSAL_NAMES)
    @pytest.mark.asyncio
    async def test_import_config_rejects_traversal(self, client, bad):
        resp = await client.post("/api/v2/backups/import-config", json={"filename": bad})
        assert resp.status_code == 422

    @pytest.mark.parametrize("bad", TRAVERSAL_NAMES)
    @pytest.mark.asyncio
    async def test_import_users_rejects_traversal(self, client, bad):
        resp = await client.post("/api/v2/backups/import-users", json={"filename": bad})
        assert resp.status_code == 422


class TestSuperadminStillWorks:
    """Регресс: валидное имя под superadmin по-прежнему проходит гейт+валидатор."""

    @pytest.mark.asyncio
    @patch("web.backend.core.backup_service.restore_database_backup", new_callable=AsyncMock)
    @patch("shared.database.db_service")
    async def test_superadmin_restore_ok(self, mock_db, mock_restore, client):
        with patch.dict("os.environ", {"DATABASE_URL": "postgresql://x/y"}):
            resp = await client.post("/api/v2/backups/restore", json={"filename": "backup.sql.gz"})
        assert resp.status_code == 200
