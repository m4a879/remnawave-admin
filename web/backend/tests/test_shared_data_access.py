"""Tests for shared/data_access.py — DB-first, API-fallback logic."""
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

pytestmark = pytest.mark.asyncio


# ── _fetch_single ───────────────────────────────────────────────


class TestFetchSingle:
    async def test_db_connected_and_found(self):
        from shared.data_access import _fetch_single
        db_mock = AsyncMock(return_value={"uuid": "abc", "name": "from_db"})
        api_mock = AsyncMock()
        with patch("shared.data_access.db_service") as svc:
            svc.is_connected = True
            result = await _fetch_single("abc", db_mock, api_mock, "node")
        assert result == {"uuid": "abc", "name": "from_db"}
        api_mock.assert_not_called()

    async def test_db_connected_but_empty_result(self):
        from shared.data_access import _fetch_single
        db_mock = AsyncMock(return_value=None)
        api_mock = AsyncMock(return_value={"response": {"uuid": "abc", "name": "from_api"}})
        with patch("shared.data_access.db_service") as svc:
            svc.is_connected = True
            result = await _fetch_single("abc", db_mock, api_mock, "node")
        assert result == {"uuid": "abc", "name": "from_api"}

    async def test_db_connected_but_missing_id_field(self):
        from shared.data_access import _fetch_single
        db_mock = AsyncMock(return_value={"name": "no_uuid"})
        api_mock = AsyncMock(return_value={"response": {"uuid": "abc", "name": "from_api"}})
        with patch("shared.data_access.db_service") as svc:
            svc.is_connected = True
            result = await _fetch_single("abc", db_mock, api_mock, "node")
        assert result == {"uuid": "abc", "name": "from_api"}

    async def test_db_disconnected_falls_to_api(self):
        from shared.data_access import _fetch_single
        db_mock = AsyncMock()
        api_mock = AsyncMock(return_value={"response": {"uuid": "abc", "name": "from_api"}})
        with patch("shared.data_access.db_service") as svc:
            svc.is_connected = False
            result = await _fetch_single("abc", db_mock, api_mock, "node")
        assert result == {"uuid": "abc", "name": "from_api"}
        db_mock.assert_not_called()

    async def test_both_fail_returns_none(self):
        from shared.data_access import _fetch_single
        db_mock = AsyncMock(return_value=None)
        api_mock = AsyncMock(side_effect=Exception("API down"))
        with patch("shared.data_access.db_service") as svc:
            svc.is_connected = True
            result = await _fetch_single("abc", db_mock, api_mock, "node")
        assert result is None

    async def test_api_returns_empty_dict(self):
        from shared.data_access import _fetch_single
        db_mock = AsyncMock(return_value=None)
        api_mock = AsyncMock(return_value={"response": {}})
        with patch("shared.data_access.db_service") as svc:
            svc.is_connected = True
            result = await _fetch_single("abc", db_mock, api_mock, "node")
        assert result is None

    async def test_api_returns_no_response_key(self):
        from shared.data_access import _fetch_single
        db_mock = AsyncMock(return_value=None)
        api_mock = AsyncMock(return_value={"data": {"uuid": "abc"}})
        with patch("shared.data_access.db_service") as svc:
            svc.is_connected = True
            result = await _fetch_single("abc", db_mock, api_mock, "node")
        assert result is None


# ── _fetch_single_wrapped ───────────────────────────────────────


class TestFetchSingleWrapped:
    async def test_db_connected_and_found(self):
        from shared.data_access import _fetch_single_wrapped
        db_mock = AsyncMock(return_value={"uuid": "abc"})
        api_mock = AsyncMock()
        with patch("shared.data_access.db_service") as svc:
            svc.is_connected = True
            result = await _fetch_single_wrapped("abc", db_mock, api_mock, "node")
        assert result == {"response": {"uuid": "abc"}}

    async def test_db_empty_falls_to_api(self):
        from shared.data_access import _fetch_single_wrapped
        db_mock = AsyncMock(return_value=None)
        api_mock = AsyncMock(return_value={"response": {"uuid": "abc", "from": "api"}})
        with patch("shared.data_access.db_service") as svc:
            svc.is_connected = True
            result = await _fetch_single_wrapped("abc", db_mock, api_mock, "node")
        assert result == {"response": {"uuid": "abc", "from": "api"}}

    async def test_db_disconnected(self):
        from shared.data_access import _fetch_single_wrapped
        db_mock = AsyncMock()
        api_mock = AsyncMock(return_value={"response": {"uuid": "abc"}})
        with patch("shared.data_access.db_service") as svc:
            svc.is_connected = False
            result = await _fetch_single_wrapped("abc", db_mock, api_mock, "node")
        assert result == {"response": {"uuid": "abc"}}

    async def test_both_fail_exception_propagates(self):
        from shared.data_access import _fetch_single_wrapped
        db_mock = AsyncMock(return_value=None)
        api_mock = AsyncMock(side_effect=Exception("fail"))
        with patch("shared.data_access.db_service") as svc:
            svc.is_connected = True
            with pytest.raises(Exception, match="fail"):
                await _fetch_single_wrapped("abc", db_mock, api_mock, "node")


# ── _fetch_list ─────────────────────────────────────────────────


class TestFetchList:
    async def test_db_connected_and_has_data(self):
        from shared.data_access import _fetch_list
        db_mock = AsyncMock(return_value=[{"uuid": "a"}, {"uuid": "b"}])
        api_mock = AsyncMock()
        with patch("shared.data_access.db_service") as svc:
            svc.is_connected = True
            result = await _fetch_list(db_mock, api_mock, "nodes")
        assert len(result) == 2
        api_mock.assert_not_called()

    async def test_db_connected_empty_list_falls_to_api(self):
        from shared.data_access import _fetch_list
        db_mock = AsyncMock(return_value=[])
        api_mock = AsyncMock(return_value={"response": [{"uuid": "from_api"}]})
        with patch("shared.data_access.db_service") as svc:
            svc.is_connected = True
            result = await _fetch_list(db_mock, api_mock, "nodes")
        assert result == [{"uuid": "from_api"}]

    async def test_db_disconnected(self):
        from shared.data_access import _fetch_list
        db_mock = AsyncMock()
        api_mock = AsyncMock(return_value={"response": [{"uuid": "api_only"}]})
        with patch("shared.data_access.db_service") as svc:
            svc.is_connected = False
            result = await _fetch_list(db_mock, api_mock, "nodes")
        assert result == [{"uuid": "api_only"}]

    async def test_both_fail_returns_empty_list(self):
        from shared.data_access import _fetch_list
        db_mock = AsyncMock(return_value=[])
        api_mock = AsyncMock(side_effect=Exception("fail"))
        with patch("shared.data_access.db_service") as svc:
            svc.is_connected = True
            result = await _fetch_list(db_mock, api_mock, "nodes")
        assert result == []


# ── _fetch_list_wrapped ─────────────────────────────────────────


class TestFetchListWrapped:
    async def test_db_connected_and_has_data(self):
        from shared.data_access import _fetch_list_wrapped
        db_mock = AsyncMock(return_value=[{"uuid": "a"}])
        api_mock = AsyncMock()
        with patch("shared.data_access.db_service") as svc:
            svc.is_connected = True
            result = await _fetch_list_wrapped(db_mock, api_mock, "nodes")
        assert result == {"response": [{"uuid": "a"}]}

    async def test_fallback_to_api_and_wraps(self):
        from shared.data_access import _fetch_list_wrapped
        db_mock = AsyncMock(return_value=[])
        api_mock = AsyncMock(return_value={"response": [{"uuid": "b"}]})
        with patch("shared.data_access.db_service") as svc:
            svc.is_connected = True
            result = await _fetch_list_wrapped(db_mock, api_mock, "nodes")
        assert result == {"response": [{"uuid": "b"}]}

    async def test_both_fail_exception_propagates(self):
        from shared.data_access import _fetch_list_wrapped
        db_mock = AsyncMock(return_value=[])
        api_mock = AsyncMock(side_effect=Exception("fail"))
        with patch("shared.data_access.db_service") as svc:
            svc.is_connected = True
            with pytest.raises(Exception, match="fail"):
                await _fetch_list_wrapped(db_mock, api_mock, "nodes")
