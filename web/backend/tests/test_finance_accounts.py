"""Тесты фазы 2 финмодуля: адаптеры хостеров, автосинк, API /finance/accounts."""
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest


# ── Реестр адаптеров ─────────────────────────────────────────────


class TestAdapterRegistry:
    def test_billmanager_and_hostkey_registered(self):
        from web.backend.core.finance.adapters import list_adapters, get_adapter

        slugs = {a["slug"] for a in list_adapters()}
        assert {"billmanager", "hostkey"} <= slugs
        assert get_adapter("billmanager").slug == "billmanager"

    def test_unknown_adapter_raises(self):
        from web.backend.core.finance.adapters import get_adapter, AdapterError

        with pytest.raises(AdapterError):
            get_adapter("nope")

    def test_meta_exposes_fields(self):
        from web.backend.core.finance.adapters import get_adapter

        meta = get_adapter("billmanager").to_meta()
        assert meta["needs_base_url"] is True
        names = {f["name"] for f in meta["fields"]}
        assert {"username", "password"} <= names

    def test_validate_credentials(self):
        from web.backend.core.finance.adapters import get_adapter, AdapterError

        adapter = get_adapter("billmanager")
        with pytest.raises(AdapterError):
            adapter.validate_credentials({"username": "", "password": ""})
        adapter.validate_credentials({"username": "u", "password": "p"})  # не кидает


# ── BILLmanager адаптер (мок httpx) ──────────────────────────────


_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _patched_client(handler):
    """Фабрика httpx.AsyncClient с MockTransport (без рекурсии на патче класса)."""
    def factory(**kw):
        kw.pop("transport", None)
        return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kw)
    return factory


class TestBillmanagerAdapter:
    @pytest.mark.asyncio
    async def test_endpoint_normalization(self):
        from web.backend.core.finance.adapters.billmanager import BillmanagerAdapter

        a = BillmanagerAdapter()
        assert a._endpoint("https://my.waicore.com") == "https://my.waicore.com/billmgr"
        assert a._endpoint("https://my.h2.nexus/billmgr?func=logon") == "https://my.h2.nexus/billmgr"
        assert a._endpoint("https://bill.1cent.host/billmgr/") == "https://bill.1cent.host/billmgr"

    @pytest.mark.asyncio
    async def test_fetch_falls_back_to_typed_when_unified_missing(self):
        """Реальный кейс h2.nexus: func=item/service нет («модуль не загружен»),
        услуги берутся из func=vds. Баланс должен подтянуться в любом случае."""
        from web.backend.core.finance.adapters.billmanager import BillmanagerAdapter

        def _not_found(func):
            return httpx.Response(200, json={"doc": {"error": {
                "$type": "missed",
                "msg": {"$": f"Не удалось найти функцию '{func}'. Возможно, управляющий модуль не загружен."},
            }}})

        def handler(request: httpx.Request) -> httpx.Response:
            func = request.url.params.get("func")
            if func == "subaccount":
                return httpx.Response(200, json={"doc": {"elem": [
                    {"balance": {"$": "1234.50"}, "currency": {"$": "usd"}},
                ]}})
            if func == "vds":
                return httpx.Response(200, json={"doc": {"elem": [
                    {"id": {"$": "801"}, "domain": {"$": "vds-de-1"}, "item_cost": {"$": "890.00"},
                     "expiredate": {"$": "2026-08-01"}, "status": {"$": "3"}},
                ]}})
            if func in ("service", "item", "dedic", "vhost", "domain", "soft", "certificate"):
                return _not_found(func)
            return httpx.Response(200, json={"doc": {}})

        adapter = BillmanagerAdapter()
        with patch("httpx.AsyncClient", _patched_client(handler)):
            result = await adapter.fetch("https://my.h2.nexus/billmgr", {"username": "u", "password": "p"})

        assert result.balance == 1234.5
        assert result.currency == "USD"
        assert len(result.services) == 1
        vds = result.services[0]
        assert vds.name == "vds-de-1"
        assert vds.price == 890.0
        assert vds.next_due_at == "2026-08-01"
        assert vds.status == "active"

    @pytest.mark.asyncio
    async def test_fetch_uses_unified_service_list_when_available(self):
        from web.backend.core.finance.adapters.billmanager import BillmanagerAdapter

        def handler(request: httpx.Request) -> httpx.Response:
            func = request.url.params.get("func")
            if func == "subaccount":
                return httpx.Response(200, json={"doc": {"elem": [
                    {"balance": {"$": "50.00"}, "currency": {"$": "eur"}},
                ]}})
            if func == "service":
                return httpx.Response(200, json={"doc": {"elem": [
                    {"id": {"$": "1"}, "name": {"$": "srv-1"}, "cost": {"$": "10"},
                     "expiredate": {"$": "2026-09-01"}, "status": {"$": "2"}},
                    {"id": {"$": "2"}, "name": {"$": "dom.ru"}, "expiredate": {"$": "2027-01-01"},
                     "status": {"$": "3"}},
                ]}})
            return httpx.Response(200, json={"doc": {}})

        adapter = BillmanagerAdapter()
        with patch("httpx.AsyncClient", _patched_client(handler)):
            result = await adapter.fetch("https://my.waicore.com", {"username": "u", "password": "p"})

        assert result.balance == 50.0
        assert len(result.services) == 2
        # цена отсутствует у домена -> None, а не 0
        assert result.services[1].price is None

    @pytest.mark.asyncio
    async def test_fetch_balance_survives_all_services_missing(self):
        """Если ни одной функции услуг нет — баланс всё равно возвращается, services=[]"""
        from web.backend.core.finance.adapters.billmanager import BillmanagerAdapter

        def handler(request: httpx.Request) -> httpx.Response:
            func = request.url.params.get("func")
            if func == "subaccount":
                return httpx.Response(200, json={"doc": {"elem": [
                    {"balance": {"$": "7.00"}, "currency": {"$": "usd"}},
                ]}})
            return httpx.Response(200, json={"doc": {"error": {
                "$type": "missed", "msg": {"$": f"Не удалось найти функцию '{func}'."},
            }}})

        adapter = BillmanagerAdapter()
        with patch("httpx.AsyncClient", _patched_client(handler)):
            result = await adapter.fetch("https://my.h2.nexus", {"username": "u", "password": "p"})

        assert result.balance == 7.0
        assert result.services == []

    @pytest.mark.asyncio
    async def test_auth_error_raises_adaptererror(self):
        from web.backend.core.finance.adapters.billmanager import BillmanagerAdapter
        from web.backend.core.finance.adapters import AdapterError

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"doc": {"error": {
                "$type": "auth", "$object": "badpassword",
                "msg": {"$": "Неверное имя пользователя или пароль"},
            }}})

        adapter = BillmanagerAdapter()
        with patch("httpx.AsyncClient", _patched_client(handler)):
            with pytest.raises(AdapterError, match="[Аа]вториз"):
                await adapter.fetch("https://my.waicore.com", {"username": "u", "password": "bad"})


# ── Hostkey адаптер ──────────────────────────────────────────────


class TestHostkeyAdapter:
    def test_base_ignores_provider_site_url(self):
        from web.backend.core.finance.adapters.hostkey import HostkeyAdapter, _DEFAULT_BASE

        a = HostkeyAdapter()
        # адрес сайта провайдера -> дефолтный invapi-эндпоинт
        assert a._base("https://hostkey.ru") == _DEFAULT_BASE
        assert a._base("") == _DEFAULT_BASE
        assert a._base(None) == _DEFAULT_BASE
        # явный invapi сохраняется
        assert a._base("https://invapi.hostkey.com") == "https://invapi.hostkey.com"

    def test_extract_token_rejects_html(self):
        from web.backend.core.finance.adapters.hostkey import HostkeyAdapter

        assert HostkeyAdapter._extract_token(httpx.Response(200, text="<html><body>site</body></html>")) is None
        assert HostkeyAdapter._extract_token(httpx.Response(200, json={"token": "TKN"})) == "TKN"
        assert HostkeyAdapter._extract_token(httpx.Response(200, text="OPAQUE-TOKEN-123")) == "OPAQUE-TOKEN-123"

    @pytest.mark.asyncio
    async def test_fetch_full_flow_via_invapi(self):
        from urllib.parse import parse_qs
        from web.backend.core.finance.adapters.hostkey import HostkeyAdapter

        hosts_seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            hosts_seen.append(request.url.host)
            path = request.url.path
            body = parse_qs(request.content.decode())
            if path.endswith("/auth.php"):
                # invapi ждёт ключ в `key`; конверт {"result":0,"token":...}
                if body.get("key"):
                    return httpx.Response(200, json={"result": 0, "token": "TKN"})
                return httpx.Response(200, json={"result": -2, "error": "auth: malformed request #1"})
            if path.endswith("/whmcs.php"):
                action = (body.get("action") or [""])[0]
                if action == "getcredits":
                    return httpx.Response(200, json={"credits": {"credit": [
                        {"amount": "10.50", "currencycode": "USD"},
                        {"amount": "4.50", "currencycode": "USD"},
                    ]}})
                if action == "getclientsproducts":
                    return httpx.Response(200, json={"products": {"product": [
                        {"id": 1, "name": "VDS-1", "recurringamount": "5.00",
                         "billingcycle": "monthly", "nextduedate": "2026-08-10", "status": "Active"},
                    ]}})
            return httpx.Response(404)

        adapter = HostkeyAdapter()
        # передаём адрес сайта провайдера — адаптер обязан уйти на invapi
        with patch("httpx.AsyncClient", _patched_client(handler)):
            result = await adapter.fetch("https://hostkey.ru", {"api_key": "KEY"})

        assert all(h.startswith("invapi.") for h in hosts_seen)
        assert result.balance == 15.0
        assert result.currency == "USD"
        assert len(result.services) == 1
        assert result.services[0].next_due_at == "2026-08-10"
        assert result.services[0].price == 5.0


# ── Автосинк ─────────────────────────────────────────────────────


def _fake_sync_result(balance=1000.0, currency="USD", services=None):
    from web.backend.core.finance.adapters.base import SyncResult, Service
    return SyncResult(balance=balance, currency=currency, services=services or [
        Service(name="vds-de-1", price=890.0, next_due_at="2026-08-01"),
    ])


class TestSync:
    @pytest.mark.asyncio
    async def test_sync_account_records_snapshot_and_due_dates(self):
        from web.backend.core.finance import sync as sync_mod

        account = {
            "id": 3, "provider_id": 7, "provider_name": "Waicore", "provider_url": None,
            "adapter": "billmanager", "base_url": "https://my.waicore.com",
            "low_balance_threshold": None, "last_alerted_at": None,
        }
        db = AsyncMock()
        db.is_connected = True
        db.get_finance_account = AsyncMock(return_value=account)
        db.get_finance_account_credentials = AsyncMock(return_value="ENC")
        db.set_finance_account_sync_result = AsyncMock()
        db.record_finance_balance_snapshot = AsyncMock()
        db.update_finance_item = AsyncMock()
        db.list_finance_items = AsyncMock(return_value=[
            {"id": 55, "name": "vds-de-1", "provider_id": 7, "next_due_at": "2026-07-01"},
        ])

        fake_adapter = AsyncMock()
        fake_adapter.fetch = AsyncMock(return_value=_fake_sync_result())

        with patch("shared.database.db_service", db), \
             patch("web.backend.core.crypto.decrypt_field", return_value='{"username":"u","password":"p"}'), \
             patch("web.backend.core.finance.sync.get_adapter", return_value=fake_adapter), \
             patch("shared.config_service.config_service") as cfg:
            cfg.get.side_effect = lambda k, d=None: d
            result = await sync_mod.sync_account(3)

        assert result["status"] == "ok"
        assert result["balance"] == 1000.0
        db.record_finance_balance_snapshot.assert_awaited_once()
        # дата списания подтянулась к данным хостера
        db.update_finance_item.assert_awaited_once()
        assert db.update_finance_item.await_args.kwargs["next_due_at"] == "2026-08-01"
        ok_kwargs = db.set_finance_account_sync_result.await_args.kwargs
        assert ok_kwargs["ok"] is True

    @pytest.mark.asyncio
    async def test_sync_account_low_balance_alerts_once(self):
        from web.backend.core.finance import sync as sync_mod

        account = {
            "id": 3, "provider_id": 7, "provider_name": "Waicore", "provider_url": "https://w",
            "adapter": "billmanager", "base_url": "https://w",
            "low_balance_threshold": 500.0, "last_alerted_at": None,
        }
        db = AsyncMock()
        db.is_connected = True
        db.get_finance_account = AsyncMock(return_value=account)
        db.get_finance_account_credentials = AsyncMock(return_value="ENC")
        db.set_finance_account_sync_result = AsyncMock()
        db.record_finance_balance_snapshot = AsyncMock()
        db.update_finance_account = AsyncMock()
        db.list_finance_items = AsyncMock(return_value=[])

        fake_adapter = AsyncMock()
        fake_adapter.fetch = AsyncMock(return_value=_fake_sync_result(balance=100.0, services=[]))
        notify = AsyncMock()

        with patch("shared.database.db_service", db), \
             patch("web.backend.core.crypto.decrypt_field", return_value='{"username":"u","password":"p"}'), \
             patch("web.backend.core.finance.sync.get_adapter", return_value=fake_adapter), \
             patch("web.backend.core.notification_service.create_notification", notify), \
             patch("shared.config_service.config_service") as cfg:
            cfg.get.side_effect = lambda k, d=None: d
            result = await sync_mod.sync_account(3)

        assert result["low_balance_alert"] is True
        notify.assert_awaited_once()
        assert notify.await_args.kwargs["event"] == "finance.low_balance"

    @pytest.mark.asyncio
    async def test_sync_account_adapter_error_marks_error(self):
        from web.backend.core.finance import sync as sync_mod
        from web.backend.core.finance.adapters import AdapterError

        account = {
            "id": 3, "provider_id": 7, "provider_name": "Waicore", "provider_url": None,
            "adapter": "billmanager", "base_url": "https://w",
            "low_balance_threshold": None, "last_alerted_at": None,
        }
        db = AsyncMock()
        db.is_connected = True
        db.get_finance_account = AsyncMock(return_value=account)
        db.get_finance_account_credentials = AsyncMock(return_value="ENC")
        db.set_finance_account_sync_result = AsyncMock()

        fake_adapter = AsyncMock()
        fake_adapter.fetch = AsyncMock(side_effect=AdapterError("Ошибка авторизации"))

        with patch("shared.database.db_service", db), \
             patch("web.backend.core.crypto.decrypt_field", return_value='{"username":"u","password":"p"}'), \
             patch("web.backend.core.finance.sync.get_adapter", return_value=fake_adapter):
            result = await sync_mod.sync_account(3)

        assert result["status"] == "error"
        assert "авториз" in result["error"].lower()
        assert db.set_finance_account_sync_result.await_args.kwargs["ok"] is False


# ── API /finance/accounts ────────────────────────────────────────


class TestAccountsApi:
    @pytest.mark.asyncio
    async def test_list_adapters_requires_auth(self, anon_client):
        resp = await anon_client.get("/api/v2/finance/adapters")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_adapters(self, client):
        resp = await client.get("/api/v2/finance/adapters")
        assert resp.status_code == 200
        slugs = {a["slug"] for a in resp.json()["items"]}
        assert "billmanager" in slugs

    @pytest.mark.asyncio
    async def test_create_account_encrypts_credentials(self, client):
        db = AsyncMock()
        db.create_finance_account = AsyncMock(return_value={"id": 9, "provider_id": 7})
        with patch("web.backend.api.v2.finance.db_service", db), \
             patch("web.backend.core.crypto.encrypt_field", return_value="ENC") as enc:
            resp = await client.post("/api/v2/finance/accounts", json={
                "provider_id": 7, "adapter": "billmanager",
                "base_url": "https://my.waicore.com",
                "credentials": {"username": "u", "password": "p"},
                "low_balance_threshold": 500,
            })
        assert resp.status_code == 200
        enc.assert_called_once()
        # креды уходят в БД зашифрованными, не в открытую
        assert db.create_finance_account.await_args.kwargs["credentials"] == "ENC"

    @pytest.mark.asyncio
    async def test_create_account_rejects_bad_credentials(self, client):
        resp = await client.post("/api/v2/finance/accounts", json={
            "provider_id": 7, "adapter": "billmanager",
            "base_url": "https://w", "credentials": {"username": "", "password": ""},
        })
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_create_account_requires_base_url_for_billmanager(self, client):
        resp = await client.post("/api/v2/finance/accounts", json={
            "provider_id": 7, "adapter": "billmanager",
            "credentials": {"username": "u", "password": "p"},
        })
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_test_connection_returns_balance(self, client):
        from web.backend.core.finance.adapters.base import SyncResult, Service

        adapter = AsyncMock()
        adapter.validate_credentials = lambda c: None
        adapter.test = AsyncMock(return_value=SyncResult(
            balance=500.0, currency="USD", services=[Service(name="x")],
        ))
        with patch("web.backend.core.finance.adapters.get_adapter", return_value=adapter):
            resp = await client.post("/api/v2/finance/accounts/test", json={
                "adapter": "billmanager", "base_url": "https://w",
                "credentials": {"username": "u", "password": "p"},
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["balance"] == 500.0
        assert len(data["services"]) == 1

    @pytest.mark.asyncio
    async def test_delete_account_requires_permission(self, operator_client):
        resp = await operator_client.delete("/api/v2/finance/accounts/1")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_import_panel_currency_param(self, client):
        importer = AsyncMock(return_value={"providers": 0, "items": 0, "payments": 0, "retagged": 3, "skipped": 0, "errors": []})
        with patch("web.backend.core.finance.importer.import_from_panel", importer):
            resp = await client.post("/api/v2/finance/import-panel?currency=EUR")
        assert resp.status_code == 200
        assert importer.await_args.kwargs["currency"] == "EUR"
