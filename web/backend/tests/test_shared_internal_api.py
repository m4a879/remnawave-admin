"""Tests for shared/internal_api.py — route factory & client selection."""
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.asyncio

from shared.internal_api import _make_route


# ── _make_route factory ─────────────────────────────────────────


class TestMakeRoute:
    """Test that _make_route generates correct method signatures and behavior."""

    def _make_mock_client(self):
        client = AsyncMock()
        client._get = AsyncMock(return_value={"result": "get"})
        client._post = AsyncMock(return_value={"result": "post"})
        client._patch = AsyncMock(return_value={"result": "patch"})
        client._delete = AsyncMock(return_value={"result": "delete"})
        return client

    async def test_get_no_params(self):
        client = self._make_mock_client()
        route = _make_route({"name": "test", "method": "GET", "path": "/api/v2/users"})
        result = await route(client)
        assert result == {"result": "get"}
        client._get.assert_called_once_with("/api/v2/users")
        client._post.assert_not_called()
        client._patch.assert_not_called()
        client._delete.assert_not_called()

    async def test_get_with_path_params(self):
        client = self._make_mock_client()
        route = _make_route({"name": "test_get", "method": "GET", "path": "/api/v2/users/{user_uuid}"})
        result = await route(client, "abc-123")
        assert result == {"result": "get"}
        client._get.assert_called_once_with("/api/v2/users/abc-123")

    async def test_post_no_body(self):
        client = self._make_mock_client()
        route = _make_route({"name": "test_post", "method": "POST", "path": "/api/v2/users"})
        result = await route(client)
        assert result == {"result": "post"}
        client._post.assert_called_once_with("/api/v2/users", json=None)

    async def test_post_with_body_kwargs(self):
        client = self._make_mock_client()
        route = _make_route({"name": "test_create", "method": "POST", "path": "/api/v2/users", "body": "kwargs"})
        result = await route(client, username="alice", is_active=True)
        assert result == {"result": "post"}
        _, kwargs = client._post.call_args
        assert kwargs["json"] == {"username": "alice", "isActive": True}

    async def test_post_with_body_kwargs_none_omitted(self):
        client = self._make_mock_client()
        route = _make_route({"name": "test_create2", "method": "POST", "path": "/api/v2/users", "body": "kwargs"})
        result = await route(client, username="alice", is_active=None)
        _, kwargs = client._post.call_args
        assert "isActive" not in kwargs["json"]

    async def test_post_body_kwargs_empty(self):
        client = self._make_mock_client()
        route = _make_route({"name": "test_create3", "method": "POST", "path": "/api/v2/users", "body": "kwargs"})
        result = await route(client)
        _, call_kwargs = client._post.call_args
        assert call_kwargs["json"] == {}

    async def test_patch_with_body_update(self):
        client = self._make_mock_client()
        route = _make_route({
            "name": "test_update", "method": "PATCH", "path": "/api/v2/users/{user_uuid}",
            "body": "update", "body_id": "user_uuid",
        })
        result = await route(client, "abc-123", username="bob")
        _, kwargs = client._patch.call_args
        path = client._patch.call_args[0][0]
        assert "abc-123" in path
        # uuid not in body when body_id matches path param provided positionally
        assert kwargs["json"]["username"] == "bob"

    async def test_patch_update_without_body_id_param(self):
        """When body_id not set, body should still collect kwargs."""
        client = self._make_mock_client()
        route = _make_route({
            "name": "test_update2", "method": "PATCH", "path": "/api/v2/items/{item_id}",
            "body": "update",
        })
        result = await route(client, "item-1", label="new")
        _, kwargs = client._patch.call_args
        assert "uuid" not in kwargs["json"]
        assert kwargs["json"]["label"] == "new"
        # Path param should be substituted
        client._patch.assert_called_once()
        call_args, _ = client._patch.call_args
        assert "/api/v2/items/item-1" in call_args[0]

    async def test_delete_route(self):
        client = self._make_mock_client()
        route = _make_route({"name": "test_del", "method": "DELETE", "path": "/api/v2/users/{user_uuid}"})
        result = await route(client, "abc-123")
        client._delete.assert_called_once_with("/api/v2/users/abc-123", json=None)

    async def test_delete_with_body(self):
        client = self._make_mock_client()
        route = _make_route({"name": "test_del2", "method": "DELETE", "path": "/api/v2/users/{user_uuid}", "body": "kwargs"})
        result = await route(client, "abc-123", reason="cleanup")
        _, kwargs = client._delete.call_args
        assert kwargs["json"]["reason"] == "cleanup"

    async def test_snake_to_camel_conversion(self):
        client = self._make_mock_client()
        route = _make_route({"name": "test_camel", "method": "POST", "path": "/api/v2/test", "body": "kwargs"})
        result = await route(client, short_id="s1", is_active=True)
        _, kwargs = client._post.call_args
        assert "shortId" in kwargs["json"]
        assert "isActive" in kwargs["json"]

    async def test_body_type_payload_sends_raw_kwargs(self):
        client = self._make_mock_client()
        route = _make_route({"name": "test_payload", "method": "POST", "path": "/api/v2/test", "body": "payload"})
        result = await route(client, some_key="value")
        _, kwargs = client._post.call_args
        assert kwargs["json"] == {"some_key": "value"}

    async def test_path_param_via_kwargs(self):
        client = self._make_mock_client()
        route = _make_route({"name": "test_kwpath", "method": "GET", "path": "/api/v2/users/{user_uuid}"})
        result = await route(client, user_uuid="xyz-789")
        client._get.assert_called_once_with("/api/v2/users/xyz-789")


# ── _ROUTE_DEFS validation ────────────────────────────────────


class TestRouteDefs:
    def test_no_duplicate_names(self):
        from shared.internal_api import _ROUTE_DEFS
        names = [d["name"] for d in _ROUTE_DEFS]
        assert len(names) == len(set(names)), "Duplicate route names found"

    def test_no_duplicate_routes(self):
        from shared.internal_api import _ROUTE_DEFS
        seen = set()
        for d in _ROUTE_DEFS:
            key = (d["method"], d["path"])
            assert key not in seen, f"Duplicate route: {key} via {d['name']}"
            seen.add(key)

    def test_all_routes_have_valid_method(self):
        from shared.internal_api import _ROUTE_DEFS
        valid = {"GET", "POST", "PATCH", "DELETE"}
        for d in _ROUTE_DEFS:
            assert d["method"] in valid, f"{d['name']}: invalid method {d['method']}"

    def test_all_routes_have_name(self):
        from shared.internal_api import _ROUTE_DEFS
        for d in _ROUTE_DEFS:
            assert d.get("name"), f"Route without name: {d}"
