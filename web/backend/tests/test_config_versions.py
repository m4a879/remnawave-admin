"""Тесты истории версий конфигов (встроенный редактор профилей)."""
from unittest.mock import AsyncMock, patch

import pytest


class TestProfileCrud:
    @pytest.mark.asyncio
    async def test_create_rename_delete(self, client):
        api = AsyncMock()
        api.create_config_profile = AsyncMock(return_value={"response": {"uuid": "u-9", "name": "New One"}})
        api.update_config_profile = AsyncMock(return_value={"response": {"uuid": "u-9", "name": "Renamed"}})
        api.delete_config_profile = AsyncMock(return_value={"response": {"isDeleted": True}})
        db = AsyncMock()
        with patch("shared.api_client.api_client", api), \
             patch("shared.database.db_service", db):
            r = await client.post("/api/v2/config-profiles", json={"name": "New One"})
            assert r.status_code == 200 and r.json()["uuid"] == "u-9"
            # в панель ушла дефолтная заготовка конфига
            sent = api.create_config_profile.await_args.args[0]
            assert sent["config"]["outbounds"][0]["tag"] == "DIRECT"

            r = await client.patch("/api/v2/config-profiles/u-9/name", json={"name": "Renamed"})
            assert r.status_code == 200
            api.update_config_profile.assert_awaited_with({"uuid": "u-9", "name": "Renamed"})

            r = await client.delete("/api/v2/config-profiles/u-9")
            assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_create_validates_name(self, client):
        # кириллица/короткое имя — валидация панельного паттерна на нашей стороне
        r = await client.post("/api/v2/config-profiles", json={"name": "П"})
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_x25519_proxy(self, client):
        api = AsyncMock()
        api.generate_x25519 = AsyncMock(
            return_value={"response": {"keypairs": [{"publicKey": "P", "privateKey": "S"}]}})
        with patch("shared.api_client.api_client", api):
            r = await client.get("/api/v2/config-profiles/tools/x25519")
        assert r.status_code == 200
        assert r.json()["keypairs"][0]["privateKey"] == "S"


class TestConfigVersions:
    @pytest.mark.asyncio
    async def test_list_versions(self, client):
        db = AsyncMock()
        db.list_config_versions = AsyncMock(return_value=[
            {"id": 5, "entity_name": "Main", "created_by": "admin",
             "created_at": "2026-07-18T10:00:00", "size_bytes": 120},
        ])
        with patch("shared.database.db_service", db):
            resp = await client.get("/api/v2/config-profiles/u-1/versions")
        assert resp.status_code == 200
        assert resp.json()["items"][0]["id"] == 5
        db.list_config_versions.assert_awaited_once_with("profile", "u-1")

    @pytest.mark.asyncio
    async def test_get_version_and_404(self, client):
        db = AsyncMock()
        db.get_config_version = AsyncMock(return_value={"id": 7, "content": "{}"})
        with patch("shared.database.db_service", db):
            ok = await client.get("/api/v2/config-profiles/versions/7")
        assert ok.status_code == 200 and ok.json()["content"] == "{}"

        db.get_config_version = AsyncMock(return_value=None)
        with patch("shared.database.db_service", db):
            missing = await client.get("/api/v2/config-profiles/versions/999")
        assert missing.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_saves_version_snapshot(self, client):
        db = AsyncMock()
        db.list_config_versions = AsyncMock(return_value=[{"id": 1}])  # бейзлайн уже есть
        db.save_config_version = AsyncMock(return_value=2)
        api = AsyncMock()
        api.update_config_profile = AsyncMock(return_value={"response": {"ok": True}})
        with patch("shared.database.db_service", db), \
             patch("shared.api_client.api_client", api):
            resp = await client.patch("/api/v2/config-profiles/u-1", json={"log": {}})
        assert resp.status_code == 200
        api.update_config_profile.assert_awaited_once_with({"uuid": "u-1", "config": {"log": {}}})
        # снапшот новой версии записан
        assert db.save_config_version.await_count == 1
        assert db.save_config_version.await_args.args[:2] == ("profile", "u-1")

    @pytest.mark.asyncio
    async def test_patch_surfaces_panel_error(self, client):
        """Бизнес-ошибка панели (500 + message) доносится текстом, а не generic 502."""
        from shared.exceptions import ServerError

        db = AsyncMock()
        db.list_config_versions = AsyncMock(return_value=[{"id": 1}])
        db.save_config_version = AsyncMock()
        api = AsyncMock()
        api.update_config_profile = AsyncMock(
            side_effect=ServerError("All inbounds must have a unique tag. [A061]", status_code=500))
        with patch("shared.database.db_service", db), \
             patch("shared.api_client.api_client", api):
            resp = await client.patch("/api/v2/config-profiles/u-1", json={"inbounds": []})
        assert resp.status_code == 400
        assert "unique tag" in resp.json()["detail"]
        db.save_config_version.assert_not_awaited()  # версия при провале не пишется

    @pytest.mark.asyncio
    async def test_patch_baseline_on_first_edit(self, client):
        """Перед первым нашим сохранением фиксируется исходный конфиг панели."""
        db = AsyncMock()
        db.list_config_versions = AsyncMock(return_value=[])  # версий ещё нет
        db.save_config_version = AsyncMock(return_value=1)
        api = AsyncMock()
        api.get_config_profile_by_uuid = AsyncMock(
            return_value={"response": {"name": "Main", "config": {"old": True}}})
        api.update_config_profile = AsyncMock(return_value={"response": {"ok": True}})
        with patch("shared.database.db_service", db), \
             patch("shared.api_client.api_client", api):
            resp = await client.patch("/api/v2/config-profiles/u-2", json={"new": True})
        assert resp.status_code == 200
        # два снапшота: бейзлайн «до» + новая версия
        assert db.save_config_version.await_count == 2
        baseline_call = db.save_config_version.await_args_list[0]
        assert baseline_call.kwargs.get("created_by") == "baseline"
