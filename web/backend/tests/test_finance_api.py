"""Тесты финансового модуля: циклы оплат, API /api/v2/finance, курсы, напоминания, импорт."""
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.db.finance import _advance_due, monthly_equivalent


# ── Unit: логика циклов ──────────────────────────────────────────


class TestAdvanceDue:
    def test_monthly_simple(self):
        assert _advance_due(date(2026, 7, 10), "monthly", None, date(2026, 7, 5)) == date(2026, 8, 10)

    def test_monthly_end_of_month(self):
        # 31 января -> 28 февраля (короткий месяц)
        assert _advance_due(date(2026, 1, 31), "monthly", None, date(2026, 2, 1)) == date(2026, 2, 28)

    def test_monthly_overdue_rolls_to_future(self):
        # просрочка на полгода: одна оплата возвращает расписание в будущее
        assert _advance_due(date(2026, 1, 1), "monthly", None, date(2026, 7, 17)) == date(2026, 8, 1)

    def test_yearly(self):
        assert _advance_due(date(2026, 3, 1), "yearly", None, date(2026, 3, 2)) == date(2027, 3, 1)

    def test_days_cycle(self):
        assert _advance_due(date(2026, 7, 1), "days", 10, date(2026, 7, 17)) == date(2026, 7, 21)

    def test_once_returns_none(self):
        assert _advance_due(date(2026, 7, 1), "once", None, date(2026, 7, 1)) is None


class TestMonthlyEquivalent:
    def test_all_cycles(self):
        assert monthly_equivalent(100, "monthly", None) == 100
        assert monthly_equivalent(1200, "yearly", None) == 100
        assert monthly_equivalent(10, "days", 10) == 30
        assert monthly_equivalent(500, "once", None) == 0


# ── API ──────────────────────────────────────────────────────────


SUMMARY_RUB = {
    "monthly": [{"month": "2026-07", "expense_rub": 5000.0, "income_rub": 12000.0, "net_rub": 7000.0}],
    "by_category": [{"category": "Ноды", "color": "#06b6d4", "monthly_rub": 4000.0}],
    "by_currency": [{"currency": "EUR", "expense_monthly": 40.0, "income_monthly": 0.0}],
    "recurring": {"expense_rub": 5000.0, "income_rub": 12000.0, "net_rub": 7000.0},
}


class TestFinanceApi:
    @pytest.mark.asyncio
    async def test_summary_requires_auth(self, anon_client):
        resp = await anon_client.get("/api/v2/finance/summary")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_summary_denied_without_permission(self, viewer_client):
        resp = await viewer_client.get("/api/v2/finance/summary")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_summary_converts_to_base_currency(self, client):
        db = AsyncMock()
        db.finance_summary = AsyncMock(return_value=SUMMARY_RUB)
        db.get_finance_rates = AsyncMock(return_value=[
            {"currency": "USD", "rate_rub": 100.0, "is_manual": False},
        ])
        with patch("web.backend.api.v2.finance.db_service", db), \
             patch("web.backend.api.v2.finance.config_service") as cfg:
            cfg.get.side_effect = lambda k, d=None: "USD" if k == "finance_base_currency" else d
            resp = await client.get("/api/v2/finance/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["base_currency"] == "USD"
        # 5000 RUB / 100 = 50 USD
        assert data["recurring"]["expense"] == 50.0
        assert data["monthly"][0]["net"] == 70.0

    @pytest.mark.asyncio
    async def test_create_item_validates_cycle(self, client):
        resp = await client.post("/api/v2/finance/items", json={
            "name": "X", "billing_cycle": "weekly",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_item_validates_kind(self, client):
        resp = await client.post("/api/v2/finance/items", json={
            "name": "X", "kind": "profit",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_mark_paid_404_on_missing(self, client):
        db = AsyncMock()
        db.mark_finance_item_paid = AsyncMock(return_value=None)
        with patch("web.backend.api.v2.finance.db_service", db):
            resp = await client.post("/api/v2/finance/items/99/paid", json={})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_mark_paid_ok(self, client):
        item = {"id": 5, "name": "Node", "next_due_at": "2026-08-17"}
        db = AsyncMock()
        db.mark_finance_item_paid = AsyncMock(return_value=item)
        with patch("web.backend.api.v2.finance.db_service", db):
            resp = await client.post(
                "/api/v2/finance/items/5/paid", json={"comment": "июль"},
            )
        assert resp.status_code == 200
        assert resp.json()["next_due_at"] == "2026-08-17"
        kwargs = db.mark_finance_item_paid.await_args.kwargs
        assert kwargs["comment"] == "июль"

    @pytest.mark.asyncio
    async def test_delete_requires_delete_permission(self, operator_client):
        resp = await operator_client.delete("/api/v2/finance/items/1")
        assert resp.status_code == 403


# ── Курсы валют ──────────────────────────────────────────────────


class TestRatesUpdate:
    @pytest.mark.asyncio
    async def test_update_skips_manual_and_uses_cbr(self):
        from web.backend.core.finance import rates as rates_mod

        db = AsyncMock()
        db.is_connected = True
        db.finance_currencies_in_use = AsyncMock(return_value=["USD", "EUR", "TRY"])
        db.get_finance_rates = AsyncMock(return_value=[
            {"currency": "TRY", "rate_rub": 3.0, "is_manual": True},
        ])
        db.upsert_finance_rate = AsyncMock()
        with patch("shared.database.db_service", db), \
             patch.object(rates_mod, "fetch_cbr_rates", AsyncMock(return_value={"USD": 92.5, "EUR": 100.1})):
            updated = await rates_mod.update_rates()
        assert updated == 2
        currencies = {c.args[0] for c in db.upsert_finance_rate.await_args_list}
        assert currencies == {"USD", "EUR"}  # TRY ручной — не трогаем, RUB не нужен

    @pytest.mark.asyncio
    async def test_fallback_to_erapi(self):
        from web.backend.core.finance import rates as rates_mod

        db = AsyncMock()
        db.is_connected = True
        db.finance_currencies_in_use = AsyncMock(return_value=["USDT"])
        db.get_finance_rates = AsyncMock(return_value=[])
        db.upsert_finance_rate = AsyncMock()
        with patch("shared.database.db_service", db), \
             patch.object(rates_mod, "fetch_cbr_rates", AsyncMock(return_value={"USD": 92.5})), \
             patch.object(rates_mod, "fetch_erapi_rates", AsyncMock(return_value={"USDT": 92.4})):
            updated = await rates_mod.update_rates()
        assert updated >= 1
        assert any(c.args[0] == "USDT" for c in db.upsert_finance_rate.await_args_list)


# ── Напоминания ──────────────────────────────────────────────────


def _upcoming_item(item_id=1, days_left=3, overdue=False, reminded=None):
    return {
        "id": item_id, "name": "Node-1", "amount": 5.0, "currency": "EUR",
        "next_due_at": "2026-07-20", "days_left": days_left, "is_overdue": overdue,
        "provider_name": "Aeza", "category_name": "Ноды", "url": None,
        "last_reminded_at": reminded,
    }


class TestReminders:
    @pytest.mark.asyncio
    async def test_sends_on_threshold(self):
        from web.backend.core.finance import reminders as rem

        db = AsyncMock()
        db.is_connected = True
        db.upcoming_finance_payments = AsyncMock(return_value=[_upcoming_item(days_left=3)])
        db.update_finance_item = AsyncMock()
        notify = AsyncMock()
        with patch("shared.database.db_service", db), \
             patch("web.backend.core.notification_service.create_notification", notify):
            sent = await rem.check_and_send_reminders()
        assert sent == 1
        notify.assert_awaited_once()
        assert "Node-1" in notify.await_args.kwargs["title"]
        db.update_finance_item.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_off_threshold_and_already_reminded(self):
        from web.backend.core.finance import reminders as rem

        today = date.today().isoformat()
        db = AsyncMock()
        db.is_connected = True
        db.upcoming_finance_payments = AsyncMock(return_value=[
            _upcoming_item(item_id=1, days_left=5),                 # не порог (7,3,1)
            _upcoming_item(item_id=2, days_left=3, reminded=today), # уже напоминали
        ])
        notify = AsyncMock()
        with patch("shared.database.db_service", db), \
             patch("web.backend.core.notification_service.create_notification", notify):
            sent = await rem.check_and_send_reminders()
        assert sent == 0
        notify.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_overdue_always_reminds_daily(self):
        from web.backend.core.finance import reminders as rem

        db = AsyncMock()
        db.is_connected = True
        db.upcoming_finance_payments = AsyncMock(return_value=[
            _upcoming_item(days_left=-2, overdue=True),
        ])
        db.update_finance_item = AsyncMock()
        notify = AsyncMock()
        with patch("shared.database.db_service", db), \
             patch("web.backend.core.notification_service.create_notification", notify):
            sent = await rem.check_and_send_reminders()
        assert sent == 1
        assert notify.await_args.kwargs["severity"] == "critical"


# ── Импорт из панельного биллинга ────────────────────────────────


class TestPanelImport:
    @pytest.mark.asyncio
    async def test_imports_providers_nodes_history(self, mock_db_acquire):
        from web.backend.core.finance import importer

        mock_conn, cm = mock_db_acquire
        mock_conn.fetchval = AsyncMock(return_value=None)  # платежей-дублей нет

        db = AsyncMock()
        db.is_connected = True
        db.acquire = lambda: cm
        db.create_finance_provider = AsyncMock(side_effect=[{"id": 11}, {"id": 12}])
        db.list_finance_categories = AsyncMock(return_value=[
            {"id": 1, "kind": "expense", "name": "Ноды"},
        ])
        db.list_finance_items = AsyncMock(return_value=[])
        db.create_finance_item = AsyncMock(return_value={"id": 21})
        db.get_node_by_uuid = AsyncMock(return_value={"name": "de-1"})
        db.get_finance_rates = AsyncMock(return_value=[{"currency": "USD", "rate_rub": 90.0}])

        api = AsyncMock()
        api.get_infra_providers = AsyncMock(return_value={"response": {"providers": [
            {"uuid": "p1", "name": "Hetzner", "loginUrl": "https://h", "faviconLink": None},
            {"uuid": "p2", "name": "Aeza", "loginUrl": None, "faviconLink": None},
        ]}})
        api.get_infra_billing_nodes = AsyncMock(return_value={"response": {"billingNodes": [
            {"uuid": "bn1", "nodeUuid": "3f339d94-0000-0000-0000-000000000001",
             "providerUuid": "p1", "nextBillingAt": "2026-08-01T00:00:00Z"},
        ]}})
        api.get_infra_billing_history = AsyncMock(return_value={"response": {"records": [
            {"uuid": "r1", "provider": {"name": "Hetzner"}, "amount": 50.0, "billedAt": "2026-06-01T00:00:00Z"},
        ]}})

        with patch("shared.database.db_service", db), \
             patch("shared.api_client.api_client", api):
            result = await importer.import_from_panel()

        assert result["providers"] == 2
        assert result["items"] == 1
        assert result["payments"] == 1
        assert result["errors"] == []
        item_kwargs = db.create_finance_item.await_args.kwargs
        assert item_kwargs["name"] == "de-1"
        assert item_kwargs["next_due_at"] == "2026-08-01"
        # безвалютные панельные суммы импортируются в валюте по умолчанию (USD)
        assert item_kwargs["currency"] == "USD"
        # paid_at в INSERT платежа — datetime.date (asyncpg отвергает str для date-параметра)
        from datetime import date as _date
        insert_call = next(c for c in mock_conn.execute.await_args_list if "INSERT INTO" in c.args[0])
        assert isinstance(insert_call.args[2], _date)

    @pytest.mark.asyncio
    async def test_bedolaga_month_sums_subscription_and_upserts(self, mock_db_acquire):
        from web.backend.core.finance import bedolaga_income as bi

        mock_conn, cm = mock_db_acquire
        mock_conn.fetchval = AsyncMock(return_value=None)  # записи за месяц ещё нет
        tx_cm = AsyncMock()
        tx_cm.__aenter__ = AsyncMock(return_value=None)
        tx_cm.__aexit__ = AsyncMock(return_value=False)
        mock_conn.transaction = MagicMock(return_value=tx_cm)
        db = AsyncMock()
        db.is_connected = True
        db.acquire = lambda: cm

        client_bd = AsyncMock()
        # первая страница — 2 платежа по 250 ₽ (25000 коп, знак минус — списание), вторая пустая
        client_bd.list_transactions = AsyncMock(side_effect=[
            {"items": [{"amount_kopeks": -25000}, {"amount_kopeks": -25000}]},
            {"items": []},
        ])
        with patch("shared.database.db_service", db), \
             patch("shared.bedolaga_client.bedolaga_client", client_bd), \
             patch("web.backend.api.v2.bedolaga.ensure_configured", lambda: None):
            result = await bi.import_month(2026, 6)

        assert result["amount"] == 500.0
        assert result["count"] == 2
        assert result["saved"] is True
        # INSERT (не UPDATE), kind='income'
        insert = next(c for c in mock_conn.execute.await_args_list if "INSERT INTO" in c.args[0])
        assert "'income'" in insert.args[0]

    @pytest.mark.asyncio
    async def test_bedolaga_income_overview_normalizes(self):
        from web.backend.core.finance import bedolaga_income as bi

        full = {"transactions": {
            "totals": {"income_rubles": 1000.0, "subscription_income_rubles": 800.0, "profit_rubles": 750.0},
            "today": {"income_rubles": 50.0, "transactions_count": 3},
            "by_payment_method": {"card": {"amount": 100000}},
        }}
        client_bd = AsyncMock()
        client_bd.get_full_stats = AsyncMock(return_value=full)
        with patch("shared.bedolaga_client.bedolaga_client", client_bd), \
             patch("web.backend.api.v2.bedolaga.ensure_configured", lambda: None):
            ov = await bi.fetch_income_overview()
        assert ov["total"]["subscription_income"] == 800.0
        assert ov["total"]["deposit_income"] == 1000.0
        assert ov["total"]["profit"] == 750.0
        assert ov["by_payment_method"]["card"] == 1000.0  # копейки → рубли

    @pytest.mark.asyncio
    async def test_skips_existing_node_items_and_duplicate_payments(self, mock_db_acquire):
        from web.backend.core.finance import importer

        mock_conn, cm = mock_db_acquire
        mock_conn.fetchval = AsyncMock(return_value=1)  # платёж уже есть

        db = AsyncMock()
        db.is_connected = True
        db.acquire = lambda: cm
        db.create_finance_provider = AsyncMock(return_value={"id": 11})
        db.list_finance_categories = AsyncMock(return_value=[])
        db.list_finance_items = AsyncMock(return_value=[
            {"node_uuid": "3f339d94-0000-0000-0000-000000000001", "name": "de-1"},
        ])
        db.create_finance_item = AsyncMock()
        db.get_finance_rates = AsyncMock(return_value=[{"currency": "USD", "rate_rub": 90.0}])

        api = AsyncMock()
        api.get_infra_providers = AsyncMock(return_value={"response": {"providers": []}})
        api.get_infra_billing_nodes = AsyncMock(return_value={"response": {"billingNodes": [
            {"uuid": "bn1", "nodeUuid": "3f339d94-0000-0000-0000-000000000001",
             "name": "de-1", "providerUuid": "p1"},
        ]}})
        api.get_infra_billing_history = AsyncMock(return_value={"response": {"records": [
            {"uuid": "r1", "provider": {"name": "Hetzner"}, "amount": 50.0, "billedAt": "2026-06-01T00:00:00Z"},
        ]}})

        with patch("shared.database.db_service", db), \
             patch("shared.api_client.api_client", api):
            result = await importer.import_from_panel()

        assert result["items"] == 0
        assert result["payments"] == 0
        assert result["skipped"] == 2
        db.create_finance_item.assert_not_awaited()
