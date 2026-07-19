"""Тесты Cloudflare DNS клиента (core/cloudflare_dns.py)."""
import json

import httpx
import pytest
from unittest.mock import patch

from web.backend.core import cloudflare_dns as cf
from web.backend.core.cloudflare_dns import CloudflareDnsError


_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _patched_client(handler):
    def factory(**kw):
        kw.pop("transport", None)
        return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kw)
    return factory


def _token():
    return patch.object(cf, "_stored_token", return_value="TESTTOKEN")


# ── Сборка тела запроса ──────────────────────────────────────────


class TestBuildPayload:
    def test_txt_has_no_proxied(self):
        p = cf._build_payload({"type": "TXT", "name": "x.com", "content": "v=spf1", "ttl": 1})
        assert "proxied" not in p and p["ttl"] == 1 and p["type"] == "TXT"

    def test_a_carries_proxied(self):
        p = cf._build_payload({"type": "A", "name": "x.com", "content": "1.2.3.4", "proxied": True})
        assert p["proxied"] is True

    def test_mx_carries_priority(self):
        p = cf._build_payload({"type": "MX", "name": "x.com", "content": "mail.x.com", "priority": 10})
        assert p["priority"] == 10


# ── Проверка токена ──────────────────────────────────────────────


class TestVerify:
    @pytest.mark.asyncio
    async def test_active(self):
        def h(r):
            return httpx.Response(200, json={"success": True, "result": {"status": "active"}})
        with patch("httpx.AsyncClient", _patched_client(h)):
            assert await cf.verify_token("T") is True

    @pytest.mark.asyncio
    async def test_inactive(self):
        def h(r):
            return httpx.Response(200, json={"success": True, "result": {"status": "disabled"}})
        with patch("httpx.AsyncClient", _patched_client(h)):
            assert await cf.verify_token("T") is False

    @pytest.mark.asyncio
    async def test_forbidden_token(self):
        def h(r):
            return httpx.Response(403, json={"success": False, "errors": [{"message": "bad"}]})
        with patch("httpx.AsyncClient", _patched_client(h)):
            assert await cf.verify_token("bad") is False


# ── Зоны и записи ────────────────────────────────────────────────


class TestZonesRecords:
    @pytest.mark.asyncio
    async def test_list_zones(self):
        def h(r):
            assert r.headers.get("Authorization") == "Bearer TESTTOKEN"
            return httpx.Response(200, json={"success": True, "result": [
                {"id": "z1", "name": "a.com", "status": "active", "paused": False}]})
        with _token(), patch("httpx.AsyncClient", _patched_client(h)):
            zs = await cf.list_zones()
        assert len(zs) == 1 and zs[0]["name"] == "a.com" and zs[0]["id"] == "z1"

    @pytest.mark.asyncio
    async def test_list_records_paginated(self):
        def h(r):
            page = r.url.params.get("page")
            if page == "1":
                return httpx.Response(200, json={"success": True, "result": [
                    {"id": "r1", "type": "A", "name": "a.com", "content": "1.2.3.4",
                     "ttl": 1, "proxied": False}],
                    "result_info": {"page": 1, "total_pages": 2}})
            return httpx.Response(200, json={"success": True, "result": [
                {"id": "r2", "type": "TXT", "name": "a.com", "content": "v", "ttl": 300}],
                "result_info": {"page": 2, "total_pages": 2}})
        with _token(), patch("httpx.AsyncClient", _patched_client(h)):
            rs = await cf.list_records("z1")
        assert len(rs) == 2 and rs[0]["type"] == "A" and rs[1]["type"] == "TXT"

    @pytest.mark.asyncio
    async def test_create_record_sends_proxied(self):
        seen = {}

        def h(r):
            seen.update(json.loads(r.content.decode()))
            return httpx.Response(200, json={"success": True, "result": {
                "id": "new", "type": "A", "name": "n.a.com", "content": "5.6.7.8",
                "ttl": 1, "proxied": True}})
        with _token(), patch("httpx.AsyncClient", _patched_client(h)):
            rec = await cf.create_record("z1", {
                "type": "A", "name": "n.a.com", "content": "5.6.7.8", "proxied": True, "ttl": 1})
        assert rec["id"] == "new" and seen["proxied"] is True and seen["type"] == "A"

    @pytest.mark.asyncio
    async def test_delete_record_uses_delete(self):
        called = {}

        def h(r):
            called["method"] = r.method
            return httpx.Response(200, json={"success": True, "result": {"id": "r1"}})
        with _token(), patch("httpx.AsyncClient", _patched_client(h)):
            await cf.delete_record("z1", "r1")
        assert called["method"] == "DELETE"

    @pytest.mark.asyncio
    async def test_api_error_raises(self):
        def h(r):
            return httpx.Response(200, json={"success": False,
                                             "errors": [{"message": "Record already exists"}]})
        with _token(), patch("httpx.AsyncClient", _patched_client(h)):
            with pytest.raises(CloudflareDnsError, match="already exists"):
                await cf.create_record("z1", {"type": "A", "name": "x", "content": "1.1.1.1"})

    @pytest.mark.asyncio
    async def test_not_configured_raises(self):
        with patch.object(cf, "_stored_token", return_value=None):
            with pytest.raises(CloudflareDnsError, match="не настроен"):
                await cf.list_zones()
