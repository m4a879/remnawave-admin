"""Tests for GET /api/v2/users/{uuid}/deeplinks."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from shared.deeplinks import decrypt_incy_link

MOCK_USER = {
    "uuid": "aaa-111",
    "username": "alice",
    "subscription_url": "https://sub.example.com/abc123",
}


class TestUserDeeplinks:
    @pytest.mark.asyncio
    @patch("shared.config_service.config_service")
    @patch("shared.database.db_service")
    async def test_deeplinks_success(self, mock_db, mock_cfg, client):
        mock_db.is_connected = True
        mock_db.get_user_by_uuid = AsyncMock(return_value=dict(MOCK_USER))
        mock_cfg.get = MagicMock(return_value="My Panel")

        resp = await client.get("/api/v2/users/aaa-111/deeplinks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["subscription_url"] == MOCK_USER["subscription_url"]

        by_id = {l["id"]: l["link"] for l in data["links"]}
        assert set(by_id) == {"happ", "v2rayng", "streisand", "hiddify", "clash", "incy"}
        assert by_id["happ"] == f"happ://add/{MOCK_USER['subscription_url']}"
        decoded = decrypt_incy_link(by_id["incy"])
        assert decoded == {"url": MOCK_USER["subscription_url"], "name": "My Panel"}

    @pytest.mark.asyncio
    @patch("shared.config_service.config_service")
    @patch("shared.database.db_service")
    async def test_deeplinks_name_falls_back_to_username(self, mock_db, mock_cfg, client):
        mock_db.is_connected = True
        mock_db.get_user_by_uuid = AsyncMock(return_value=dict(MOCK_USER))
        mock_cfg.get = MagicMock(return_value="")

        resp = await client.get("/api/v2/users/aaa-111/deeplinks")
        assert resp.status_code == 200
        by_id = {l["id"]: l["link"] for l in resp.json()["links"]}
        assert decrypt_incy_link(by_id["incy"])["name"] == "alice"

    @pytest.mark.asyncio
    @patch("shared.database.db_service")
    async def test_deeplinks_no_subscription_url(self, mock_db, client):
        mock_db.is_connected = True
        mock_db.get_user_by_uuid = AsyncMock(
            return_value={"uuid": "aaa-111", "username": "alice", "subscription_url": None}
        )
        resp = await client.get("/api/v2/users/aaa-111/deeplinks")
        assert resp.status_code == 404
