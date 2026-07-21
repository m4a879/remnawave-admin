"""Тесты DNS-провайдеров (core/dns/*): Cloudflare, Timeweb, reg.ru + реестр/креды."""
import json

import httpx
import pytest
from unittest.mock import patch


_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _patched_client(handler):
    def factory(**kw):
        kw.pop("transport", None)
        return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kw)
    return factory


# ── Реестр ───────────────────────────────────────────────────────


class TestRegistry:
    def test_providers_registered(self):
        from web.backend.core import dns

        slugs = {p.slug for p in dns.list_providers()}
        assert {"cloudflare", "timeweb", "regru", "selectel", "aeza"} <= slugs
        assert dns.get_provider("cloudflare").proxyable == ["A", "AAAA", "CNAME"]
        assert dns.get_provider("regru").supports_ttl is False
        assert dns.get_provider("timeweb").proxyable == []

    def test_unknown_raises(self):
        from web.backend.core import dns
        with pytest.raises(dns.DnsProviderError):
            dns.get_provider("nope")


# ── Cloudflare ───────────────────────────────────────────────────


class TestCloudflare:
    @pytest.mark.asyncio
    async def test_verify_zones_records(self):
        from web.backend.core.dns.cloudflare import CloudflareProvider

        def h(request: httpx.Request) -> httpx.Response:
            assert request.headers.get("Authorization") == "Bearer T"
            p = request.url.path
            if p == "/client/v4/user/tokens/verify":
                # Account owned tokens этим эндпоинтом отвергаются, хотя для
                # зон/записей валидны — verify НЕ должен на него ходить
                return httpx.Response(400, json={
                    "success": False, "errors": [{"message": "Invalid API Token"}]})
            if p == "/client/v4/zones":
                return httpx.Response(200, json={"success": True, "result": [
                    {"id": "z1", "name": "a.com"}]})
            if p == "/client/v4/zones/z1/dns_records":
                return httpx.Response(200, json={"success": True, "result": [
                    {"id": "r1", "type": "A", "name": "a.com", "content": "1.2.3.4",
                     "ttl": 1, "proxied": True}], "result_info": {"page": 1, "total_pages": 1}})
            return httpx.Response(404)

        prov = CloudflareProvider()
        with patch("httpx.AsyncClient", _patched_client(h)):
            assert await prov.verify({"token": "T"}) is True
            zs = await prov.list_zones({"token": "T"})
            rs = await prov.list_records({"token": "T"}, "z1")
        assert zs[0].name == "a.com"
        assert rs[0].type == "A" and rs[0].proxied is True

    @pytest.mark.asyncio
    async def test_create_sends_proxied(self):
        from web.backend.core.dns.cloudflare import CloudflareProvider

        seen = {}

        def h(request):
            seen.update(json.loads(request.content.decode()))
            return httpx.Response(200, json={"success": True, "result": {
                "id": "n", "type": "A", "name": "x.a.com", "content": "5.6.7.8",
                "proxied": True, "ttl": 1}})

        with patch("httpx.AsyncClient", _patched_client(h)):
            rec = await CloudflareProvider().create_record({"token": "T"}, "z1", {
                "type": "A", "name": "x.a.com", "content": "5.6.7.8", "proxied": True, "ttl": 1})
        assert rec.id == "n" and seen["proxied"] is True and seen["type"] == "A"

    @pytest.mark.asyncio
    async def test_verify_false_on_forbidden(self):
        from web.backend.core.dns.cloudflare import CloudflareProvider

        def h(request):
            return httpx.Response(403, json={"success": False, "errors": [{"message": "bad"}]})

        with patch("httpx.AsyncClient", _patched_client(h)):
            assert await CloudflareProvider().verify({"token": "bad"}) is False


# ── Timeweb Cloud ────────────────────────────────────────────────


class TestTimeweb:
    @pytest.mark.asyncio
    async def test_zones_records_create(self):
        from web.backend.core.dns.timeweb import TimewebProvider

        seen = {}

        def h(request: httpx.Request) -> httpx.Response:
            assert request.headers.get("Authorization") == "Bearer T"
            p, m = request.url.path, request.method
            if p == "/api/v1/domains":
                return httpx.Response(200, json={"domains": [{"fqdn": "a.com"}]})
            if p == "/api/v1/domains/a.com/dns-records" and m == "GET":
                return httpx.Response(200, json={"dns_records": [
                    {"id": 55, "type": "A", "data": {"value": "1.2.3.4", "subdomain": "www"}, "ttl": 3600}]})
            if p == "/api/v1/domains/a.com/dns-records" and m == "POST":
                seen.update(json.loads(request.content.decode()))
                return httpx.Response(201, json={"dns_record": {
                    "id": 66, "type": "A", "data": {"value": "5.6.7.8", "subdomain": "api"}, "ttl": 300}})
            return httpx.Response(404)

        prov = TimewebProvider()
        with patch("httpx.AsyncClient", _patched_client(h)):
            zs = await prov.list_zones({"token": "T"})
            rs = await prov.list_records({"token": "T"}, "a.com")
            rec = await prov.create_record({"token": "T"}, "a.com", {
                "type": "A", "name": "api", "content": "5.6.7.8", "ttl": 300})
        assert zs[0].id == "a.com"
        assert rs[0].name == "www" and rs[0].content == "1.2.3.4"
        assert seen["subdomain"] == "api" and seen["value"] == "5.6.7.8" and seen["ttl"] == 300
        assert rec.id == "66"


# ── reg.ru ───────────────────────────────────────────────────────


class TestRegru:
    @pytest.mark.asyncio
    async def test_zones_records_synthetic_id(self):
        from web.backend.core.dns.regru import RegruProvider, _unid

        def h(request: httpx.Request) -> httpx.Response:
            p = request.url.path
            assert dict(request.url.params).get("username") == "u"
            if p.endswith("/domain/get_list"):
                return httpx.Response(200, json={"result": "success",
                                                 "answer": {"domains": [{"dname": "a.com"}]}})
            if p.endswith("/zone/get_resource_records"):
                return httpx.Response(200, json={"result": "success", "answer": {"domains": [
                    {"dname": "a.com", "rrs": [
                        {"subname": "www", "rectype": "A", "content": "1.2.3.4"}]}]}})
            return httpx.Response(404)

        prov = RegruProvider()
        with patch("httpx.AsyncClient", _patched_client(h)):
            zs = await prov.list_zones({"username": "u", "password": "p"})
            rs = await prov.list_records({"username": "u", "password": "p"}, "a.com")
        assert zs[0].name == "a.com"
        r = rs[0]
        assert r.type == "A" and r.name == "www" and r.content == "1.2.3.4"
        assert _unid(r.id) == ("www", "A", "1.2.3.4")

    @pytest.mark.asyncio
    async def test_create_a_then_delete(self):
        from web.backend.core.dns.regru import RegruProvider

        calls = []

        def h(request):
            p = request.url.path
            input_data = json.loads(dict(request.url.params).get("input_data", "{}"))
            calls.append((p.split("/")[-1], input_data))
            return httpx.Response(200, json={"result": "success", "answer": {}})

        prov = RegruProvider()
        with patch("httpx.AsyncClient", _patched_client(h)):
            rec = await prov.create_record({"username": "u", "password": "p"}, "a.com", {
                "type": "A", "name": "www", "content": "9.9.9.9"})
            await prov.delete_record({"username": "u", "password": "p"}, "a.com", rec.id)

        assert calls[0][0] == "add_alias" and calls[0][1]["ipaddr"] == "9.9.9.9"
        assert calls[1][0] == "remove_record" and calls[1][1]["content"] == "9.9.9.9"

    @pytest.mark.asyncio
    async def test_result_error_raises(self):
        from web.backend.core.dns.regru import RegruProvider
        from web.backend.core.dns import DnsProviderError

        def h(request):
            return httpx.Response(200, json={"result": "error", "error_text": "Auth"})

        with patch("httpx.AsyncClient", _patched_client(h)):
            with pytest.raises(DnsProviderError):
                await RegruProvider().list_zones({"username": "u", "password": "bad"})


# ── Selectel ─────────────────────────────────────────────────────


class TestSelectelDns:
    @pytest.mark.asyncio
    async def test_zones_records_create(self):
        from web.backend.core.dns.selectel import SelectelProvider

        seen = {}

        def h(request: httpx.Request) -> httpx.Response:
            assert request.headers.get("X-Token") == "STATIC"
            p, m = request.url.path, request.method
            if p == "/domains/v1/" and m == "GET":
                return httpx.Response(200, json=[{"id": 101, "name": "a.com"}])
            if p == "/domains/v1/101/records/" and m == "GET":
                return httpx.Response(200, json=[
                    {"id": 9, "type": "A", "name": "www.a.com", "content": "1.2.3.4", "ttl": 3600}])
            if p == "/domains/v1/101/records/" and m == "POST":
                seen.update(json.loads(request.content.decode()))
                return httpx.Response(200, json={
                    "id": 10, "type": "A", "name": "api.a.com", "content": "5.6.7.8", "ttl": 300})
            return httpx.Response(404)

        prov = SelectelProvider()
        with patch("httpx.AsyncClient", _patched_client(h)):
            zs = await prov.list_zones({"token": "STATIC"})
            rs = await prov.list_records({"token": "STATIC"}, "101")
            rec = await prov.create_record({"token": "STATIC"}, "101", {
                "type": "A", "name": "api.a.com", "content": "5.6.7.8", "ttl": 300})
        assert zs[0].id == "101" and zs[0].name == "a.com"
        assert rs[0].name == "www.a.com" and rs[0].content == "1.2.3.4"
        assert seen["type"] == "A" and seen["content"] == "5.6.7.8" and seen["ttl"] == 300
        assert rec.id == "10"

    @pytest.mark.asyncio
    async def test_verify_false_on_forbidden(self):
        from web.backend.core.dns.selectel import SelectelProvider

        def h(request):
            return httpx.Response(401, json={"error": "bad"})

        with patch("httpx.AsyncClient", _patched_client(h)):
            assert await SelectelProvider().verify({"token": "bad"}) is False


# ── Aeza ─────────────────────────────────────────────────────────


class TestAezaDns:
    @pytest.mark.asyncio
    async def test_zones_records_create(self):
        from web.backend.core.dns.aeza import AezaProvider

        seen = {}

        def h(request: httpx.Request) -> httpx.Response:
            assert request.headers.get("X-API-KEY") == "KEY"
            p, m = request.url.path, request.method
            if p == "/api/v2/domains" and m == "GET":
                return httpx.Response(200, json={"data": {"items": [
                    {"id": 3413, "name": "example.com"}]}})
            if p == "/api/v2/domains/3413/records" and m == "GET":
                return httpx.Response(200, json={"data": {"items": [
                    {"id": 1, "type": "A", "name": "www", "content": "1.2.3.4", "ttl": 3600}]}})
            if p == "/api/v2/domains/3413/records" and m == "POST":
                seen.update(json.loads(request.content.decode()))
                return httpx.Response(201, json={"data": {
                    "id": 2, "type": "A", "name": "api", "content": "5.6.7.8"}})
            return httpx.Response(404)

        prov = AezaProvider()
        with patch("httpx.AsyncClient", _patched_client(h)):
            zs = await prov.list_zones({"api_key": "KEY"})
            rs = await prov.list_records({"api_key": "KEY"}, "3413")
            rec = await prov.create_record({"api_key": "KEY"}, "3413", {
                "type": "A", "name": "api", "content": "5.6.7.8"})
        assert zs[0].id == "3413" and zs[0].name == "example.com"
        assert rs[0].name == "www" and rs[0].content == "1.2.3.4"
        assert seen["type"] == "A" and seen["content"] == "5.6.7.8" and seen["name"] == "api"
        assert rec.id == "2"

    @pytest.mark.asyncio
    async def test_verify_false_on_forbidden(self):
        from web.backend.core.dns.aeza import AezaProvider

        def h(request):
            return httpx.Response(403, json={"error": "bad"})

        with patch("httpx.AsyncClient", _patched_client(h)):
            assert await AezaProvider().verify({"api_key": "bad"}) is False


# ── Хранение кредов ──────────────────────────────────────────────


class TestCredsStorage:
    def test_get_creds_decrypts_json(self):
        from web.backend.core import dns
        with patch("web.backend.core.dns.base.decrypt_field", return_value='{"token":"X"}'), \
             patch("shared.config_service.config_service") as cfg:
            cfg.get.return_value = "ENC"
            assert dns.get_creds("cloudflare") == {"token": "X"}

    def test_get_creds_none_when_empty(self):
        from web.backend.core import dns
        with patch("shared.config_service.config_service") as cfg:
            cfg.get.return_value = None
            assert dns.get_creds("cloudflare") is None


class TestTimewebPagination:
    """Timeweb: limit ≤ 500 (limit=1000 давал 400 и «записи не грузятся»)."""

    def _provider(self, pages):
        from unittest.mock import AsyncMock
        from web.backend.core.dns.timeweb import TimewebProvider
        p = TimewebProvider()
        p._req = AsyncMock(side_effect=pages)
        return p

    @pytest.mark.asyncio
    async def test_records_single_page(self):
        pages = [{
            "meta": {"total": 2},
            "dns_records": [
                {"id": 1, "type": "A", "ttl": 600, "data": {"value": "1.2.3.4"}},
                {"id": 2, "type": "TXT", "ttl": 600,
                 "data": {"subdomain": "www", "value": "v=spf1"}},
            ],
        }]
        p = self._provider(pages)
        recs = await p.list_records({"token": "t"}, "stijoin.com")
        assert [r.name for r in recs] == ["@", "www"]
        # запрос ушёл с допустимым лимитом ≤ 500
        url = p._req.await_args_list[0].args[2]
        assert "limit=500" in url and "limit=1000" not in url

    @pytest.mark.asyncio
    async def test_records_paginated(self):
        first = {"meta": {"total": 501},
                 "dns_records": [{"id": i, "type": "A", "data": {"value": "x"}}
                                 for i in range(500)]}
        second = {"meta": {"total": 501},
                  "dns_records": [{"id": 500, "type": "A", "data": {"value": "x"}}]}
        p = self._provider([first, second])
        recs = await p.list_records({"token": "t"}, "z")
        assert len(recs) == 501
        assert p._req.await_count == 2
        assert "offset=500" in p._req.await_args_list[1].args[2]

    @pytest.mark.asyncio
    async def test_zones_paginated(self):
        first = {"meta": {"total": 101},
                 "domains": [{"fqdn": f"d{i}.com"} for i in range(100)]}
        second = {"meta": {"total": 101}, "domains": [{"fqdn": "last.com"}]}
        p = self._provider([first, second])
        zones = await p.list_zones({"token": "t"})
        assert len(zones) == 101
        assert zones[-1].name == "last.com"
