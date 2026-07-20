"""Тесты пресетов создания юзера."""
from unittest.mock import AsyncMock, patch

import pytest


class TestUserPresets:
    @pytest.mark.asyncio
    async def test_crud_flow(self, client):
        db = AsyncMock()
        db.list_user_presets = AsyncMock(return_value=[])
        db.create_user_preset = AsyncMock(return_value={
            "id": 1, "name": "Trial", "data": {"expire_days": 3, "hwid_device_limit": 1},
        })
        db.update_user_preset = AsyncMock(return_value={"id": 1, "name": "Trial+", "data": {}})
        db.delete_user_preset = AsyncMock(return_value=True)
        with patch("shared.database.db_service", db):
            lst = await client.get("/api/v2/user-presets")
            assert lst.status_code == 200 and lst.json()["items"] == []

            created = await client.post("/api/v2/user-presets", json={
                "name": "Trial",
                "data": {"expire_days": 3, "hwid_device_limit": 1, "junk": "x"},
            })
            assert created.status_code == 200 and created.json()["id"] == 1
            # мусорные ключи отсеяны перед записью
            saved_data = db.create_user_preset.await_args.args[1]
            assert "junk" not in saved_data and saved_data["expire_days"] == 3

            upd = await client.patch("/api/v2/user-presets/1", json={"name": "Trial+"})
            assert upd.status_code == 200

            dele = await client.delete("/api/v2/user-presets/1")
            assert dele.status_code == 200

    @pytest.mark.asyncio
    async def test_duplicate_name_400(self, client):
        db = AsyncMock()
        db.create_user_preset = AsyncMock(return_value=None)  # UNIQUE конфликт -> None
        with patch("shared.database.db_service", db):
            r = await client.post("/api/v2/user-presets", json={"name": "Dup", "data": {}})
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_validation_rejects_bad_values(self, client):
        # отрицательный лимит устройств -> 422 (pydantic ge=0)
        r = await client.post("/api/v2/user-presets", json={
            "name": "Bad", "data": {"hwid_device_limit": -5},
        })
        assert r.status_code == 422
