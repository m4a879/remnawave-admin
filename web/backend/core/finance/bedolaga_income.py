"""Доходы из Bedolaga Bot API для финансового модуля.

Живой виджет — три метрики из /stats/full (пополнения / выручка с подписок /
профит, за всё время + сегодня + разбивка по способам оплаты).

Импорт в историю — ТОЛЬКО выручка с подписок (subscription_payment) за месяц:
пополнения баланса не доход (это приток на счёт юзера, обязательство до
траты), а профит финмодуль считает сам как доход − расход. Писать и deposit,
и subscription как income = двойной учёт.
"""
import asyncio
import logging
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

INCOME_ITEM_NAME = "Выручка Bedolaga (подписки)"
DEPOSIT_ITEM_NAME = "Пополнения Bedolaga"
DEPOSIT_SOURCE = "bedolaga_deposit"
DEPOSIT_SYNC_INTERVAL_SECONDS = 6 * 3600


def _rub(block: Dict[str, Any], key: str) -> float:
    try:
        return round(float(block.get(f"{key}_rubles") or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _pm_amount(v: Any) -> float:
    """Сумма способа оплаты в рублях. Bedolaga отдаёт разные формы, поэтому
    приоритет — явные единицы (*_rubles as-is, *_kopeks/100), иначе эвристика."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return round(float(v) / 100, 2)  # голое число трактуем как копейки
    if isinstance(v, dict):
        for k in ("amount_rubles", "sum_rubles", "total_rubles", "rubles"):
            if v.get(k) is not None:
                try:
                    return round(float(v[k]), 2)
                except (TypeError, ValueError):
                    pass
        for k in ("amount_kopeks", "sum_kopeks", "amount", "sum", "total"):
            if v.get(k) is not None:
                try:
                    return round(float(v[k]) / 100, 2)
                except (TypeError, ValueError):
                    pass
    return 0.0


def _tx_date(t: Dict[str, Any]) -> Optional[str]:
    """Дата транзакции (YYYY-MM-DD) из вероятных полей."""
    for k in ("created_at", "completed_at", "date", "paid_at", "updated_at"):
        v = t.get(k)
        if v:
            s = str(v).strip().replace("T", " ")
            d = s.split(" ")[0]
            if len(d) == 10 and d[4] == "-":
                return d
    return None


async def fetch_income_overview() -> Dict[str, Any]:
    """Нормализованные метрики дохода из /stats/full (для живого виджета)."""
    from web.backend.api.v2.bedolaga import proxy_request
    from shared.bedolaga_client import bedolaga_client

    full = await proxy_request(bedolaga_client.get_full_stats)
    tx = (full or {}).get("transactions") or {}
    totals = tx.get("totals") or {}
    today = tx.get("today") or {}
    raw_pm = tx.get("by_payment_method") or {}
    logger.info("Bedolaga by_payment_method raw: %s", str(raw_pm)[:300])

    return {
        "currency": "RUB",
        "total": {
            "deposit_income": _rub(totals, "income"),
            "subscription_income": _rub(totals, "subscription_income"),
            "profit": _rub(totals, "profit"),
        },
        "today": {
            "deposit_income": _rub(today, "income"),
            "transactions_count": today.get("transactions_count") or 0,
        },
        "month": {
            "deposit_income": await _month_deposit_total(),
        },
        "by_payment_method": {m: _pm_amount(v) for m, v in raw_pm.items()},
    }


async def _month_deposit_total() -> float:
    """Сумма записанных пополнений Bedolaga за текущий месяц (RUB), из истории."""
    from shared.database import db_service
    from shared.db_schema import FINANCE_PAYMENTS_TABLE

    if not db_service.is_connected:
        return 0.0
    async with db_service.acquire() as conn:
        val = await conn.fetchval(
            f"""SELECT COALESCE(SUM(amount), 0) FROM {FINANCE_PAYMENTS_TABLE}
                WHERE source = $1
                  AND paid_at >= date_trunc('month', CURRENT_DATE)::date""",
            DEPOSIT_SOURCE,
        )
    try:
        return round(float(val or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _month_bounds(year: int, month: int) -> tuple[datetime, datetime, date]:
    last_day = monthrange(year, month)[1]
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    end = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)
    return start, end, date(year, month, last_day)


async def import_month(year: int, month: int) -> Dict[str, Any]:
    """Сумма subscription_payment за месяц → одна income-запись в finance_payments.

    Идемпотентно: повторный импорт того же месяца обновляет сумму (не плодит).
    """
    from web.backend.api.v2.bedolaga import proxy_request, ensure_configured
    from shared.bedolaga_client import bedolaga_client
    from shared.database import db_service
    from shared.db_schema import FINANCE_PAYMENTS_TABLE

    ensure_configured()
    start, end, paid_date = _month_bounds(year, month)
    month_key = f"{year:04d}-{month:02d}"

    total_kopeks = 0
    count = 0
    offset = 0
    page = 200
    while True:
        resp = await proxy_request(
            lambda o=offset: bedolaga_client.list_transactions(
                limit=page, offset=o, type="subscription_payment",
                date_from=start.isoformat(), date_to=end.isoformat(),
                is_completed=True,
            )
        )
        items = (resp or {}).get("items") or (resp or {}).get("transactions") or []
        if not items:
            break
        for t in items:
            total_kopeks += abs(int(t.get("amount_kopeks") or 0))
            count += 1
        if len(items) < page:
            break
        offset += page
        if offset > 100_000:  # предохранитель
            logger.warning("Bedolaga import: pagination guard hit at offset %d", offset)
            break

    amount = round(total_kopeks / 100, 2)
    comment = f"Импорт из Bedolaga за {month_key} ({count} платежей)"

    if not db_service.is_connected:
        return {"month": month_key, "amount": amount, "count": count, "saved": False}

    async with db_service.acquire() as conn:
        async with conn.transaction():
            existing = await conn.fetchval(
                f"""SELECT id FROM {FINANCE_PAYMENTS_TABLE}
                    WHERE source = 'bedolaga' AND item_name = $1 AND paid_at = $2""",
                INCOME_ITEM_NAME, paid_date,
            )
            if existing:
                await conn.execute(
                    f"""UPDATE {FINANCE_PAYMENTS_TABLE}
                        SET amount = $1, comment = $2 WHERE id = $3""",
                    amount, comment, existing,
                )
            else:
                await conn.execute(
                    f"""INSERT INTO {FINANCE_PAYMENTS_TABLE}
                        (item_id, item_name, kind, paid_at, amount, currency, rate_rub, comment, source)
                        VALUES (NULL, $1, 'income', $2, $3, 'RUB', 1, $4, 'bedolaga')""",
                    INCOME_ITEM_NAME, paid_date, amount, comment,
                )

    logger.info("Bedolaga income imported: %s = %.2f RUB (%d payments)", month_key, amount, count)
    return {"month": month_key, "amount": amount, "count": count, "saved": True}


async def record_daily_deposits(lookback_days: int = 40) -> Dict[str, Any]:
    """Пополнения Bedolaga → пер-дневные income-платежи (source='bedolaga_deposit').

    Тянет deposit-транзакции за окно lookback_days, группирует по дню и upsert'ит
    одну income-запись на день. Бэкфилл окна делает текущий месяц точным, даже
    если задача включилась в его середине; повторный прогон переписывает суммы.
    ⚠️ Пополнения = деньги на входе; НЕ совмещать с месячным импортом выручки
    подписок (import_month), иначе двойной учёт дохода.
    """
    from web.backend.api.v2.bedolaga import proxy_request, ensure_configured
    from shared.bedolaga_client import bedolaga_client
    from shared.database import db_service
    from shared.db_schema import FINANCE_PAYMENTS_TABLE

    ensure_configured()
    if not db_service.is_connected:
        return {"days": 0, "saved": False}

    today = date.today()
    start_dt = datetime(today.year, today.month, today.day, tzinfo=timezone.utc) - timedelta(days=lookback_days)
    end_dt = datetime(today.year, today.month, today.day, 23, 59, 59, tzinfo=timezone.utc)

    by_day: Dict[str, int] = {}
    offset, page = 0, 200
    while True:
        resp = await proxy_request(
            lambda o=offset: bedolaga_client.list_transactions(
                limit=page, offset=o, type="deposit",
                date_from=start_dt.isoformat(), date_to=end_dt.isoformat(),
                is_completed=True,
            )
        )
        items = (resp or {}).get("items") or (resp or {}).get("transactions") or []
        if not items:
            break
        for t in items:
            d = _tx_date(t)
            if not d:
                continue
            by_day[d] = by_day.get(d, 0) + abs(int(t.get("amount_kopeks") or 0))
        if len(items) < page:
            break
        offset += page
        if offset > 200_000:
            logger.warning("Bedolaga deposits: pagination guard hit at offset %d", offset)
            break

    saved = 0
    async with db_service.acquire() as conn:
        for d, kopeks in by_day.items():
            amount = round(kopeks / 100, 2)
            updated = await conn.execute(
                f"""UPDATE {FINANCE_PAYMENTS_TABLE}
                    SET amount = $1 WHERE source = $2 AND paid_at = $3::date""",
                amount, DEPOSIT_SOURCE, d,
            )
            if "UPDATE 0" in updated:
                await conn.execute(
                    f"""INSERT INTO {FINANCE_PAYMENTS_TABLE}
                        (item_id, item_name, kind, paid_at, amount, currency, rate_rub, comment, source)
                        VALUES (NULL, $1, 'income', $2::date, $3, 'RUB', 1, 'Пополнения Bedolaga за день', $4)""",
                    DEPOSIT_ITEM_NAME, d, amount, DEPOSIT_SOURCE,
                )
            saved += 1

    if saved:
        logger.info("Bedolaga deposits recorded: %d days", saved)
    return {"days": saved, "saved": True}


async def deposits_loop() -> None:
    """Периодическая запись пополнений Bedolaga (запускается в lifespan)."""
    from shared.config_service import config_service

    await asyncio.sleep(180)
    while True:
        try:
            if config_service.get("finance_bedolaga_deposits_enabled", True):
                await record_daily_deposits()
        except Exception as e:
            logger.warning("Bedolaga deposits loop failed: %s", e)
        await asyncio.sleep(DEPOSIT_SYNC_INTERVAL_SECONDS)
