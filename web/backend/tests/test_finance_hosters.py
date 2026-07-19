"""Тесты нативных адаптеров хостеров: Timeweb, Aeza, Hetzner, Selectel."""
import json

import httpx
import pytest
from unittest.mock import patch


_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _patched_client(handler):
    """httpx.AsyncClient с MockTransport (без рекурсии на патче класса)."""
    def factory(**kw):
        kw.pop("transport", None)
        return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kw)
    return factory


# ── Реестр ───────────────────────────────────────────────────────


class TestRegistry:
    def test_all_hosters_registered(self):
        from web.backend.core.finance.adapters import list_adapters, get_adapter

        slugs = {a["slug"] for a in list_adapters()}
        expected = {"timeweb", "aeza", "hetzner", "selectel",
                    "vultr", "vdsina", "cloudflare", "porkbun", "regru"}
        assert expected <= slugs
        for slug in expected:
            a = get_adapter(slug)
            assert a.slug == slug
            assert a.to_meta()["needs_base_url"] is False
            assert a.to_meta()["fields"]  # есть хотя бы одно поле


# ── Timeweb ──────────────────────────────────────────────────────


class TestTimeweb:
    @pytest.mark.asyncio
    async def test_fetch_balance_and_servers_with_preset_price(self):
        from web.backend.core.finance.adapters.timeweb import TimewebAdapter

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers.get("Authorization") == "Bearer TKN"
            p = request.url.path
            if p == "/api/v1/account/finances":
                return httpx.Response(200, json={"finances": {"balance": 1234.5, "currency": "rub"}})
            if p == "/api/v1/servers":
                return httpx.Response(200, json={"servers": [{
                    "id": 10, "name": "node-de", "preset_id": 5, "status": "on",
                    "cpu": 2, "ram": 2048, "location": "de-1",
                    "networks": [{"type": "public", "ips": [
                        {"type": "ipv4", "ip": "1.2.3.4", "is_main": True}]}],
                }]})
            if p == "/api/v1/presets/servers":
                return httpx.Response(200, json={"server_presets": [
                    {"id": 5, "price": 400.0, "location": "de-1"}]})
            return httpx.Response(404)

        adapter = TimewebAdapter()
        with patch("httpx.AsyncClient", _patched_client(handler)):
            r = await adapter.fetch(None, {"token": "TKN"})

        assert r.balance == 1234.5 and r.currency == "RUB"
        assert len(r.services) == 1
        s = r.services[0]
        assert s.name == "node-de" and s.price == 400.0 and s.currency == "RUB"
        assert s.period == "monthly" and s.next_due_at is None
        assert s.ips == ["1.2.3.4"] and s.external_id == "10"

    @pytest.mark.asyncio
    async def test_auth_error(self):
        from web.backend.core.finance.adapters.timeweb import TimewebAdapter
        from web.backend.core.finance.adapters import AdapterError

        def handler(request):
            return httpx.Response(401, json={"message": "unauthorized"})

        with patch("httpx.AsyncClient", _patched_client(handler)):
            with pytest.raises(AdapterError, match="[Аа]вториз"):
                await TimewebAdapter().fetch(None, {"token": "bad"})

    @pytest.mark.asyncio
    async def test_missing_token(self):
        from web.backend.core.finance.adapters.timeweb import TimewebAdapter
        from web.backend.core.finance.adapters import AdapterError

        with pytest.raises(AdapterError):
            await TimewebAdapter().fetch(None, {})


# ── Aeza ─────────────────────────────────────────────────────────


class TestAeza:
    @pytest.mark.asyncio
    async def test_fetch_minor_units_and_filters_deleted(self):
        from web.backend.core.finance.adapters.aeza import AezaAdapter

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers.get("X-API-KEY") == "KEY"
            p = request.url.path
            if p == "/api/v2/accounts/me":
                return httpx.Response(200, json={"data": {"balance": 50000, "currency": "eur"}})
            if p == "/api/v2/services":
                return httpx.Response(200, json={"data": {"items": [
                    {"id": 1, "name": "vps-nl", "ip": "5.6.7.8", "price": 79900,
                     "paymentTerm": "month", "expiresAt": "2026-08-15T00:00:00Z",
                     "status": "active", "locationCode": "nl"},
                    {"id": 2, "name": "gone", "status": "deleted"},
                ]}})
            return httpx.Response(404)

        adapter = AezaAdapter()
        with patch("httpx.AsyncClient", _patched_client(handler)):
            r = await adapter.fetch(None, {"api_key": "KEY"})

        assert r.balance == 500.0 and r.currency == "EUR"
        assert len(r.services) == 1  # deleted отфильтрован
        s = r.services[0]
        assert s.name == "vps-nl" and s.price == 799.0 and s.currency == "EUR"
        assert s.period == "monthly" and s.next_due_at == "2026-08-15"
        assert s.ips == ["5.6.7.8"]

    @pytest.mark.asyncio
    async def test_iso_from_unix_timestamp(self):
        from web.backend.core.finance.adapters.aeza import _iso

        from datetime import datetime, timezone

        assert _iso("2026-08-15T10:00:00Z") == "2026-08-15"
        assert _iso("2026-08-15") == "2026-08-15"
        ts = int(datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc).timestamp())
        assert _iso(ts) == "2026-08-15"          # unix seconds (UTC)
        assert _iso(ts * 1000) == "2026-08-15"   # миллисекунды
        assert _iso(0) is None
        assert _iso(None) is None


# ── Hetzner ──────────────────────────────────────────────────────


class TestHetzner:
    @pytest.mark.asyncio
    async def test_fetch_servers_price_by_location_no_balance(self):
        from web.backend.core.finance.adapters.hetzner import HetznerAdapter

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers.get("Authorization") == "Bearer HZ"
            if request.url.path == "/v1/servers":
                return httpx.Response(200, json={
                    "servers": [{
                        "id": 7, "name": "hz-1", "status": "running",
                        "public_net": {"ipv4": {"ip": "9.10.11.12"}},
                        "server_type": {"name": "cpx21", "cores": 3, "memory": 4, "disk": 80,
                            "prices": [
                                {"location": "nbg1", "price_monthly": {"gross": "8.4900"}},
                                {"location": "fsn1", "price_monthly": {"gross": "9.9900"}},
                            ]},
                        "datacenter": {"name": "nbg1-dc3",
                            "location": {"name": "nbg1", "city": "Nuremberg", "country": "DE"}},
                    }],
                    "meta": {"pagination": {"next_page": None}}})
            return httpx.Response(404)

        adapter = HetznerAdapter()
        with patch("httpx.AsyncClient", _patched_client(handler)):
            r = await adapter.fetch(None, {"token": "HZ"})

        assert r.balance is None and r.currency == "EUR"
        assert len(r.services) == 1
        s = r.services[0]
        assert s.name == "hz-1" and s.price == 8.49  # цена по локации сервера (nbg1)
        assert s.currency == "EUR" and s.ips == ["9.10.11.12"]
        assert "3 vCPU" in s.specs and "Nuremberg" in s.specs


# ── Selectel ─────────────────────────────────────────────────────


class TestSelectel:
    @pytest.mark.asyncio
    async def test_keystone_then_balance(self):
        from web.backend.core.finance.adapters.selectel import SelectelAdapter

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "identity/v3/auth/tokens" in url:
                return httpx.Response(201, headers={"X-Subject-Token": "KTOKEN"},
                                      json={"token": {}})
            if request.url.path == "/v3/balances":
                assert request.headers.get("X-Auth-Token") == "KTOKEN"
                return httpx.Response(200, json={"data": {
                    "billings": [{"final_sum": 250000}],
                    "settings": {"currency": "rub"},
                }})
            return httpx.Response(404)

        adapter = SelectelAdapter()
        with patch("httpx.AsyncClient", _patched_client(handler)):
            r = await adapter.fetch(None, {
                "account_id": "123456", "username": "svc", "password": "p"})

        assert r.balance == 2500.0 and r.currency == "RUB"
        assert r.services == []

    @pytest.mark.asyncio
    async def test_keystone_auth_error(self):
        from web.backend.core.finance.adapters.selectel import SelectelAdapter
        from web.backend.core.finance.adapters import AdapterError

        def handler(request):
            return httpx.Response(401, json={"error": {"message": "bad creds"}})

        with patch("httpx.AsyncClient", _patched_client(handler)):
            with pytest.raises(AdapterError, match="[Аа]вториз"):
                await SelectelAdapter().fetch(None, {
                    "account_id": "1", "username": "u", "password": "bad"})

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        from web.backend.core.finance.adapters.selectel import SelectelAdapter
        from web.backend.core.finance.adapters import AdapterError

        with pytest.raises(AdapterError):
            await SelectelAdapter().fetch(None, {"account_id": "1"})


# ── Vultr ────────────────────────────────────────────────────────


class TestVultr:
    @pytest.mark.asyncio
    async def test_balance_and_instance_price_by_plan(self):
        from web.backend.core.finance.adapters.vultr import VultrAdapter

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers.get("Authorization") == "Bearer VK"
            p = request.url.path
            if p == "/v2/account":
                return httpx.Response(200, json={"account": {"balance": 42.5, "pending_charges": 3}})
            if p == "/v2/plans":
                return httpx.Response(200, json={
                    "plans": [{"id": "vc2-1c-1gb", "monthly_cost": 6}],
                    "meta": {"links": {"next": ""}}})
            if p == "/v2/instances":
                return httpx.Response(200, json={
                    "instances": [{
                        "id": "abc", "label": "vpn-us", "main_ip": "10.20.30.40",
                        "plan": "vc2-1c-1gb", "region": "ewr", "status": "active",
                        "vcpu_count": 1, "ram": 1024}],
                    "meta": {"links": {"next": ""}}})
            return httpx.Response(404)

        with patch("httpx.AsyncClient", _patched_client(handler)):
            r = await VultrAdapter().fetch(None, {"token": "VK"})

        assert r.balance == 42.5 and r.currency == "USD"
        s = r.services[0]
        assert s.name == "vpn-us" and s.price == 6.0 and s.currency == "USD"
        assert s.ips == ["10.20.30.40"] and "1 vCPU" in s.specs


# ── VDSina ───────────────────────────────────────────────────────


class TestVdsina:
    @pytest.mark.asyncio
    async def test_balance_and_servers_envelope(self):
        from web.backend.core.finance.adapters.vdsina import VdsinaAdapter

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers.get("Authorization") == "TKN"
            p = request.url.path
            if p == "/v1/account.balance":
                return httpx.Response(200, json={"status": "ok", "data": {"real": 355.2, "bonus": 0}})
            if p == "/v1/server":
                return httpx.Response(200, json={"status": "ok", "data": [{
                    "id": 5, "name": "srv-ru", "status": "active",
                    "ip": [{"ip": "77.88.1.2"}],
                    "server-plan": {"id": 3, "name": "Plan-2", "cost": 430, "period": "month"}}]})
            return httpx.Response(404)

        with patch("httpx.AsyncClient", _patched_client(handler)):
            r = await VdsinaAdapter().fetch(None, {"token": "TKN"})

        assert r.balance == 355.2 and r.currency == "RUB"
        s = r.services[0]
        assert s.name == "srv-ru" and s.price == 430.0 and s.period == "monthly"
        assert s.ips == ["77.88.1.2"] and s.specs == "Plan-2"

    @pytest.mark.asyncio
    async def test_error_envelope_raises(self):
        from web.backend.core.finance.adapters.vdsina import VdsinaAdapter
        from web.backend.core.finance.adapters import AdapterError

        def handler(request):
            return httpx.Response(200, json={"status": "error", "data": "Invalid token"})

        with patch("httpx.AsyncClient", _patched_client(handler)):
            with pytest.raises(AdapterError, match="VDSina"):
                await VdsinaAdapter().fetch(None, {"token": "bad"})


# ── Cloudflare (домены) ──────────────────────────────────────────


class TestCloudflare:
    @pytest.mark.asyncio
    async def test_autodetect_account_and_domains(self):
        from web.backend.core.finance.adapters.cloudflare import CloudflareAdapter

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers.get("Authorization") == "Bearer CF"
            p = request.url.path
            if p == "/client/v4/accounts":
                return httpx.Response(200, json={"success": True,
                                                 "result": [{"id": "acc123", "name": "My"}]})
            if p == "/client/v4/accounts/acc123/registrar/domains":
                return httpx.Response(200, json={"success": True, "result": [{
                    "id": "d1", "name": "example.com", "expires_at": "2027-03-01T00:00:00Z",
                    "auto_renew": True, "last_known_status": "active"}],
                    "result_info": {"page": 1, "total_pages": 1}})
            return httpx.Response(404)

        with patch("httpx.AsyncClient", _patched_client(handler)):
            r = await CloudflareAdapter().fetch(None, {"token": "CF"})

        assert r.balance is None and r.currency == "USD"
        s = r.services[0]
        assert s.name == "example.com" and s.next_due_at == "2027-03-01"
        assert s.period == "yearly" and s.specs == "автопродление"

    @pytest.mark.asyncio
    async def test_auth_error_raises(self):
        from web.backend.core.finance.adapters.cloudflare import CloudflareAdapter
        from web.backend.core.finance.adapters import AdapterError

        def handler(request):
            return httpx.Response(403, json={"success": False,
                                             "errors": [{"message": "Invalid token"}]})

        with patch("httpx.AsyncClient", _patched_client(handler)):
            with pytest.raises(AdapterError, match="[Аа]вториз"):
                await CloudflareAdapter().fetch(None, {"token": "bad"})


# ── Porkbun (домены) ─────────────────────────────────────────────


class TestPorkbun:
    @pytest.mark.asyncio
    async def test_domains_and_optional_balance(self):
        from web.backend.core.finance.adapters.porkbun import PorkbunAdapter

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content.decode() or "{}")
            assert body.get("apikey") == "pk" and body.get("secretapikey") == "sk"
            p = request.url.path
            if p == "/api/json/v3/account/balance":
                return httpx.Response(200, json={"status": "SUCCESS", "balance": "12.34"})
            if p == "/api/json/v3/domain/listAll":
                return httpx.Response(200, json={"status": "SUCCESS", "domains": [{
                    "domain": "mysite.io", "status": "ACTIVE", "tld": "io",
                    "expireDate": "2026-12-31 23:59:59", "autoRenew": "1"}]})
            return httpx.Response(404)

        with patch("httpx.AsyncClient", _patched_client(handler)):
            r = await PorkbunAdapter().fetch(None, {"apikey": "pk", "secretapikey": "sk"})

        assert r.balance == 12.34
        s = r.services[0]
        assert s.name == "mysite.io" and s.next_due_at == "2026-12-31"
        assert s.specs == "автопродление"

    @pytest.mark.asyncio
    async def test_error_status_raises(self):
        from web.backend.core.finance.adapters.porkbun import PorkbunAdapter
        from web.backend.core.finance.adapters import AdapterError

        def handler(request):
            return httpx.Response(200, json={"status": "ERROR", "message": "Invalid API key"})

        with patch("httpx.AsyncClient", _patched_client(handler)):
            with pytest.raises(AdapterError, match="Porkbun"):
                await PorkbunAdapter().fetch(None, {"apikey": "x", "secretapikey": "y"})


# ── reg.ru ───────────────────────────────────────────────────────


class TestRegru:
    @pytest.mark.asyncio
    async def test_services_list(self):
        from web.backend.core.finance.adapters.regru import RegruAdapter

        def handler(request: httpx.Request) -> httpx.Response:
            params = dict(request.url.params)
            assert params.get("username") == "u" and params.get("password") == "p"
            if request.url.path.endswith("/service/get_list"):
                return httpx.Response(200, json={"result": "success", "answer": {"services": [{
                    "service_id": "1", "servname": "mydomain.ru", "servtype": "domain",
                    "state": "active", "cost": "199.00", "expiration_date": "2027-05-20"}]}})
            return httpx.Response(404)

        with patch("httpx.AsyncClient", _patched_client(handler)):
            r = await RegruAdapter().fetch(None, {"username": "u", "password": "p"})

        assert r.currency == "RUB"
        s = r.services[0]
        assert s.name == "mydomain.ru" and s.price == 199.0
        assert s.next_due_at == "2027-05-20" and s.specs == "domain"

    @pytest.mark.asyncio
    async def test_error_result_raises(self):
        from web.backend.core.finance.adapters.regru import RegruAdapter
        from web.backend.core.finance.adapters import AdapterError

        def handler(request):
            return httpx.Response(200, json={"result": "error",
                                             "error_text": "Auth failed", "error_code": "AUTH"})

        with patch("httpx.AsyncClient", _patched_client(handler)):
            with pytest.raises(AdapterError, match="reg.ru"):
                await RegruAdapter().fetch(None, {"username": "u", "password": "bad"})
