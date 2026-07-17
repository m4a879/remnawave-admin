"""Доходы из Bedolaga Bot API для финансового модуля.

Живой виджет — три метрики из /stats/full (пополнения / выручка с подписок /
профит, за всё время + сегодня + разбивка по способам оплаты).

Импорт в историю — ТОЛЬКО выручка с подписок (subscription_payment) за месяц:
пополнения баланса не доход (это приток на счёт юзера, обязательство до
траты), а профит финмодуль считает сам как доход − расход. Писать и deposit,
и subscription как income = двойной учёт.
"""
import logging
from calendar import monthrange
from datetime import date, datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)

INCOME_ITEM_NAME = "Выручка Bedolaga (подписки)"


def _rub(block: Dict[str, Any], key: str) -> float:
    try:
        return round(float(block.get(f"{key}_rubles") or 0), 2)
    except (TypeError, ValueError):
        return 0.0


async def fetch_income_overview() -> Dict[str, Any]:
    """Нормализованные метрики дохода из /stats/full (для живого виджета)."""
    from web.backend.api.v2.bedolaga import proxy_request
    from shared.bedolaga_client import bedolaga_client

    full = await proxy_request(bedolaga_client.get_full_stats)
    tx = (full or {}).get("transactions") or {}
    totals = tx.get("totals") or {}
    today = tx.get("today") or {}

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
        "by_payment_method": {
            m: round(float((v or {}).get("amount", 0) or 0) / 100, 2)
            for m, v in (tx.get("by_payment_method") or {}).items()
        },
    }


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
