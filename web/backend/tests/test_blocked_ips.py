"""Tests for blocked IPs — /api/v2/blocked-ips/*."""
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock, MagicMock

from web.backend.api.deps import get_current_admin
from .conftest import make_admin


MOCK_BLOCKED_IP_ROW = {
    "id": 1,
    "ip_cidr": "10.0.0.1/32",
    "reason": "Brute force",
    "added_by_admin_id": 1,
    "added_by_username": "superadmin_user",
    "country_code": "US",
    "asn_org": "Example ISP",
    "expires_at": None,
    "created_at": datetime(2026, 3, 20, 12, 0, 0, tzinfo=timezone.utc),
}

MOCK_BLOCKED_IP_ROW_2 = {
    **MOCK_BLOCKED_IP_ROW,
    "id": 2,
    "ip_cidr": "192.168.1.0/24",
    "reason": "Subnet block",
}


def _mock_db_service(
    get_blocked_ips_return=None,
    get_blocked_ips_count_return=0,
    add_blocked_ip_return=None,
    remove_blocked_ip_return=False,
    get_all_active_blocked_ips_return=None,
):
    """Create a mock db_service with blocked IP methods."""
    mock_svc = MagicMock()
    mock_svc.is_connected = True
    mock_svc.get_blocked_ips = AsyncMock(return_value=get_blocked_ips_return or [])
    mock_svc.get_blocked_ips_count = AsyncMock(return_value=get_blocked_ips_count_return)
    mock_svc.add_blocked_ip = AsyncMock(return_value=add_blocked_ip_return)
    mock_svc.remove_blocked_ip = AsyncMock(return_value=remove_blocked_ip_return)
    mock_svc.get_all_active_blocked_ips = AsyncMock(
        return_value=get_all_active_blocked_ips_return or []
    )

    # acquire() context manager for push_blocklist_to_agents
    mock_conn = AsyncMock()
    mock_svc.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_svc.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_svc


class TestListBlockedIPs:
    """GET /api/v2/blocked-ips."""

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.blocked_ips.push_blocklist_to_agents", new_callable=AsyncMock, return_value=0)
    async def test_list_empty(self, mock_push, client, mock_db_acquire):
        mock_db, cm = mock_db_acquire

        mock_svc = _mock_db_service(
            get_blocked_ips_return=[],
            get_blocked_ips_count_return=0,
        )
        from web.backend.api.deps import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_svc

        resp = await client.get("/api/v2/blocked-ips")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.blocked_ips.push_blocklist_to_agents", new_callable=AsyncMock, return_value=0)
    async def test_list_with_items(self, mock_push, client, mock_db_acquire):
        mock_db, cm = mock_db_acquire

        mock_svc = _mock_db_service(
            get_blocked_ips_return=[MOCK_BLOCKED_IP_ROW],
            get_blocked_ips_count_return=1,
        )
        from web.backend.api.deps import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_svc

        resp = await client.get("/api/v2/blocked-ips")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["ip_cidr"] == "10.0.0.1/32"
        assert data["total"] == 1


class TestAddBlockedIP:
    """POST /api/v2/blocked-ips."""

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.blocked_ips.push_blocklist_to_agents", new_callable=AsyncMock, return_value=0)
    @patch("web.backend.core.rbac.write_audit_log", new_callable=AsyncMock)
    async def test_add_valid_ip(self, mock_audit, mock_push, client, mock_db_acquire):
        mock_db, cm = mock_db_acquire
        created_row = {**MOCK_BLOCKED_IP_ROW, "ip_cidr": "203.0.113.5/32"}

        mock_svc = _mock_db_service(add_blocked_ip_return=created_row)
        from web.backend.api.deps import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_svc

        with patch("web.backend.api.v2.blocked_ips._enrich_geoip", return_value={}):
            resp = await client.post(
                "/api/v2/blocked-ips",
                json={"ip_cidr": "203.0.113.5", "reason": "Test block"},
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["ip_cidr"] == "203.0.113.5/32"

    @pytest.mark.asyncio
    async def test_add_invalid_ip(self, client):
        """Pydantic validation rejects invalid IP — 422."""
        resp = await client.post(
            "/api/v2/blocked-ips",
            json={"ip_cidr": "not-an-ip"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.blocked_ips.push_blocklist_to_agents", new_callable=AsyncMock, return_value=0)
    @patch("web.backend.core.rbac.write_audit_log", new_callable=AsyncMock)
    async def test_add_duplicate(self, mock_audit, mock_push, client, mock_db_acquire):
        mock_db, cm = mock_db_acquire

        mock_svc = _mock_db_service(add_blocked_ip_return=None)  # None = duplicate
        from web.backend.api.deps import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_svc

        with patch("web.backend.api.v2.blocked_ips._enrich_geoip", return_value={}):
            resp = await client.post(
                "/api/v2/blocked-ips",
                json={"ip_cidr": "10.0.0.1/32"},
            )
        assert resp.status_code == 409


class TestDeleteBlockedIP:
    """DELETE /api/v2/blocked-ips/{ip_id}."""

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.blocked_ips.push_blocklist_to_agents", new_callable=AsyncMock, return_value=0)
    @patch("web.backend.core.rbac.write_audit_log", new_callable=AsyncMock)
    async def test_delete_success(self, mock_audit, mock_push, client, mock_db_acquire):
        mock_db, cm = mock_db_acquire

        mock_svc = _mock_db_service(remove_blocked_ip_return=True)
        from web.backend.api.deps import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_svc

        resp = await client.delete("/api/v2/blocked-ips/1")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.blocked_ips.push_blocklist_to_agents", new_callable=AsyncMock, return_value=0)
    async def test_delete_not_found(self, mock_push, client, mock_db_acquire):
        mock_db, cm = mock_db_acquire

        mock_svc = _mock_db_service(remove_blocked_ip_return=False)
        from web.backend.api.deps import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_svc

        resp = await client.delete("/api/v2/blocked-ips/999")
        assert resp.status_code == 404


class TestViewerCannotAdd:
    """Viewer role should not have blocked_ips:create permission."""

    @pytest.mark.asyncio
    async def test_viewer_cannot_add(self, app, viewer):
        """POST /api/v2/blocked-ips should return 403 for viewer."""
        from httpx import ASGITransport, AsyncClient

        app.dependency_overrides[get_current_admin] = lambda: viewer
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v2/blocked-ips",
                json={"ip_cidr": "1.2.3.4"},
            )
        assert resp.status_code == 403


class TestBulkAdd:
    """POST /api/v2/blocked-ips/bulk."""

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.blocked_ips.push_blocklist_to_agents", new_callable=AsyncMock, return_value=2)
    @patch("web.backend.core.rbac.write_audit_log", new_callable=AsyncMock)
    async def test_bulk_add(self, mock_audit, mock_push, client, mock_db_acquire):
        mock_db, cm = mock_db_acquire
        row1 = {**MOCK_BLOCKED_IP_ROW, "id": 10, "ip_cidr": "1.1.1.0/24"}
        row2 = {**MOCK_BLOCKED_IP_ROW, "id": 11, "ip_cidr": "2.2.2.0/24"}

        mock_svc = _mock_db_service()
        # First call returns row (added), second returns None (skipped/dup)
        mock_svc.add_blocked_ip = AsyncMock(side_effect=[row1, None])
        from web.backend.api.deps import get_db
        client._transport.app.dependency_overrides[get_db] = lambda: mock_svc

        with patch("web.backend.api.v2.blocked_ips._enrich_geoip", return_value={}):
            resp = await client.post(
                "/api/v2/blocked-ips/bulk",
                json={
                    "ips": ["1.1.1.0/24", "2.2.2.0/24"],
                    "reason": "Bulk test",
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["added"] == 1
        assert data["skipped"] == 1
        assert data["synced_agents"] == 2


class TestSyncEndpoint:
    """POST /api/v2/blocked-ips/sync."""

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.blocked_ips.push_blocklist_to_agents", new_callable=AsyncMock, return_value=3)
    async def test_sync(self, mock_push, client):
        resp = await client.post("/api/v2/blocked-ips/sync")
        assert resp.status_code == 200
        data = resp.json()
        assert data["synced_agents"] == 3
        mock_push.assert_awaited_once()


class TestPushBlocklistFormat:
    """push_blocklist_to_agents шлёт ПЛОСКИЙ подписанный payload.

    Контракт с агентом: {"type": "sync_blocked_ips", ..., "_ts", "_sig"} —
    агент проверяет HMAC по payload без _sig. Раньше пуш заворачивался в
    {"type": "command", "payload", "signature"} и агент его отбрасывал
    («Unknown command type: command»).
    """

    @pytest.mark.asyncio
    async def test_flat_signed_payload(self):
        from web.backend.api.v2 import blocked_ips as mod

        mock_svc = _mock_db_service(
            get_all_active_blocked_ips_return=["10.0.0.1/32", "192.168.1.0/24"]
        )
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"agent_token": "tok-123"}
        acquire_cm = MagicMock()
        acquire_cm.__aenter__ = AsyncMock(return_value=mock_conn)
        acquire_cm.__aexit__ = AsyncMock(return_value=False)
        mock_svc.acquire.return_value = acquire_cm

        sent = []

        async def _capture(node_uuid, payload):
            sent.append((node_uuid, payload))
            return True

        mock_am = MagicMock()
        mock_am.list_connected.return_value = ["node-1"]
        mock_am.send_command = AsyncMock(side_effect=_capture)

        with patch("shared.database.db_service", mock_svc), \
             patch("web.backend.core.agent_manager.agent_manager", mock_am):
            count = await mod.push_blocklist_to_agents()

        assert count == 1
        node_uuid, payload = sent[0]
        assert node_uuid == "node-1"
        # Плоский формат — тип команды виден агенту сразу
        assert payload["type"] == "sync_blocked_ips"
        assert payload["ips"] == ["10.0.0.1/32", "192.168.1.0/24"]
        assert payload["mode"] == "replace"
        assert "_ts" in payload and "_sig" in payload

        # Подпись валидна с точки зрения агента (HMAC по payload без _sig)
        import hashlib
        import hmac as hmac_mod
        import json
        from web.backend.core.config import get_web_settings

        body = {k: v for k, v in payload.items() if k != "_sig"}
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
        key = hashlib.sha256(
            f"{get_web_settings().secret_key}:tok-123".encode()
        ).digest()
        expected = hmac_mod.new(key, canonical.encode(), hashlib.sha256).hexdigest()
        assert payload["_sig"] == expected
