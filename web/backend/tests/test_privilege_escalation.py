"""Privilege-escalation tests (H5 admins, H6 roles).

Делегированный админ имеет admins:*/roles:* но НЕ является superadmin и не
владеет некоторыми правами (settings:edit). Он не должен уметь через эти
эндпоинты повысить себя или другого выше собственного набора прав.
"""
import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport

from web.backend.api.deps import get_current_admin
from .conftest import make_admin

# admins:*/roles:* есть, а settings:edit — НЕТ (это и есть потолок эскалации).
DELEGATED_PERMS = {
    ("admins", "view"), ("admins", "create"), ("admins", "edit"), ("admins", "delete"),
    ("roles", "view"), ("roles", "create"), ("roles", "edit"), ("roles", "delete"),
    ("users", "view"),
}


@pytest_asyncio.fixture()
async def delegated_client(app):
    delegated = make_admin(role="manager", username="delegated", account_id=7,
                           permissions=DELEGATED_PERMS)
    app.dependency_overrides[get_current_admin] = lambda: delegated
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── H5: admins ──────────────────────────────────────────────────

class TestAdminRoleEscalation:
    @pytest.mark.asyncio
    @patch("web.backend.api.v2.admins.get_all_permissions_for_role_id", new_callable=AsyncMock)
    @patch("web.backend.api.v2.admins.get_role_by_id", new_callable=AsyncMock)
    async def test_cannot_create_admin_with_superadmin_role(self, mock_role, mock_perms, delegated_client):
        mock_role.return_value = {"id": 1, "name": "superadmin"}
        mock_perms.return_value = set()
        resp = await delegated_client.post("/api/v2/admins", json={
            "username": "victim", "password": "Str0ng!Passw0rd", "role_id": 1,
        })
        assert resp.status_code == 403

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.admins.get_all_permissions_for_role_id", new_callable=AsyncMock)
    @patch("web.backend.api.v2.admins.get_role_by_id", new_callable=AsyncMock)
    async def test_cannot_create_admin_with_broader_role(self, mock_role, mock_perms, delegated_client):
        mock_role.return_value = {"id": 5, "name": "poweruser"}
        # роль содержит settings:edit, которого у делегата нет
        mock_perms.return_value = {("settings", "edit")}
        resp = await delegated_client.post("/api/v2/admins", json={
            "username": "victim", "password": "Str0ng!Passw0rd", "role_id": 5,
        })
        assert resp.status_code == 403

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.admins.get_admin_account_by_id", new_callable=AsyncMock)
    async def test_cannot_edit_superadmin_account(self, mock_get, delegated_client):
        mock_get.return_value = {"id": 2, "username": "root", "role_id": 1, "role_name": "superadmin"}
        resp = await delegated_client.put("/api/v2/admins/2", json={"email": "x@y.z"})
        assert resp.status_code == 403


# ── H6: roles ───────────────────────────────────────────────────

class TestRoleEscalation:
    @pytest.mark.asyncio
    async def test_cannot_create_role_with_broader_permissions(self, delegated_client):
        # settings:edit вне набора делегата → 403 (валидатор ресурсов проходит,
        # subset-гард отклоняет)
        resp = await delegated_client.post("/api/v2/roles", json={
            "name": "escalated", "display_name": "X",
            "permissions": [{"resource": "settings", "action": "edit"}],
        })
        assert resp.status_code == 403

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.roles.get_role_by_id", new_callable=AsyncMock)
    async def test_cannot_edit_system_role(self, mock_get, delegated_client):
        mock_get.return_value = {"id": 3, "name": "admin", "is_system": True, "role_id": 3}
        resp = await delegated_client.put("/api/v2/roles/3", json={
            "permissions": [{"resource": "users", "action": "view"}],
        })
        assert resp.status_code == 403

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.roles.get_role_by_id", new_callable=AsyncMock)
    async def test_cannot_edit_own_role(self, mock_get, delegated_client):
        # делегат имеет role_id=1 (из make_admin) — правка своей роли запрещена
        mock_get.return_value = {"id": 1, "name": "delegated_role", "is_system": False}
        resp = await delegated_client.put("/api/v2/roles/1", json={
            "permissions": [{"resource": "users", "action": "view"}],
        })
        assert resp.status_code == 403

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.roles.update_role", new_callable=AsyncMock)
    @patch("web.backend.api.v2.roles.get_role_by_id", new_callable=AsyncMock)
    async def test_can_edit_nonsystem_role_within_own_perms(self, mock_get, mock_update, delegated_client):
        mock_get.return_value = {"id": 9, "name": "helper", "is_system": False}
        mock_update.return_value = {"id": 9, "name": "helper", "display_name": "H",
                                    "permissions": [{"resource": "users", "action": "view"}], "is_system": False}
        resp = await delegated_client.put("/api/v2/roles/9", json={
            "permissions": [{"resource": "users", "action": "view"}],
        })
        assert resp.status_code == 200
