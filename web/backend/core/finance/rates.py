"""Курсы валют для финансового модуля.

Источник — ЦБ РФ (XML_daily), fallback — open.er-api.com. Все курсы хранятся
как rate_rub (сколько рублей за единицу валюты); конвертация между любыми
валютами идёт кросс-курсом через RUB. Курсы, поправленные вручную
(is_manual), автообновлением не перезаписываются.
"""
import asyncio
import logging
import xml.etree.ElementTree as ET
from typing import Dict, Iterable, Optional

import httpx

logger = logging.getLogger(__name__)

CBR_URL = "https://www.cbr.ru/scripts/XML_daily.asp"
ERAPI_URL = "https://open.er-api.com/v6/latest/RUB"
UPDATE_INTERVAL_SECONDS = 24 * 3600


async def fetch_cbr_rates() -> Dict[str, float]:
    """Курсы ЦБ РФ: {"USD": 92.5, ...} — рублей за единицу валюты."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(CBR_URL)
        resp.raise_for_status()
    root = ET.fromstring(resp.text)
    rates: Dict[str, float] = {}
    for valute in root.findall("Valute"):
        code = (valute.findtext("CharCode") or "").strip().upper()
        nominal = float((valute.findtext("Nominal") or "1").replace(",", "."))
        value = float((valute.findtext("Value") or "0").replace(",", "."))
        if code and value > 0 and nominal > 0:
            rates[code] = value / nominal
    return rates


async def fetch_erapi_rates() -> Dict[str, float]:
    """open.er-api.com: base=RUB отдаёт единиц валюты за 1 RUB -> инвертируем."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(ERAPI_URL)
        resp.raise_for_status()
        data = resp.json()
    out: Dict[str, float] = {}
    for code, per_rub in (data.get("rates") or {}).items():
        try:
            per_rub = float(per_rub)
            if per_rub > 0:
                out[str(code).upper()] = 1.0 / per_rub
        except (TypeError, ValueError):
            continue
    return out


async def update_rates(currencies: Optional[Iterable[str]] = None) -> int:
    """Обновить курсы нужных валют в БД. Возвращает число обновлённых.

    currencies=None -> валюты активных записей + базовая + USD/EUR.
    """
    from shared.database import db_service
    from shared.config_service import config_service

    if not db_service.is_connected:
        return 0

    base = str(config_service.get("finance_base_currency", "RUB") or "RUB").upper()
    if currencies is None:
        in_use = await db_service.finance_currencies_in_use()
        currencies = set(in_use) | {base, "USD", "EUR"}
    wanted = {c.upper() for c in currencies if c and c.upper() != "RUB"}
    if not wanted:
        return 0

    manual = {
        r["currency"] for r in await db_service.get_finance_rates() if r.get("is_manual")
    }
    wanted -= manual
    if not wanted:
        return 0

    rates: Dict[str, float] = {}
    try:
        rates = await fetch_cbr_rates()
    except Exception as e:
        logger.warning("CBR rates fetch failed: %s", e)
    missing = wanted - set(rates)
    if missing:
        try:
            fallback = await fetch_erapi_rates()
            for code in missing:
                if code in fallback:
                    rates[code] = fallback[code]
        except Exception as e:
            logger.warning("er-api rates fetch failed: %s", e)

    updated = 0
    for code in sorted(wanted):
        if code in rates:
            await db_service.upsert_finance_rate(code, rates[code], is_manual=False)
            updated += 1
        else:
            logger.warning("No rate found for currency %s", code)
    if updated:
        logger.info("Finance rates updated: %d currencies", updated)
    return updated


async def rates_update_loop() -> None:
    """Суточный цикл автообновления курсов (запускается в lifespan)."""
    from shared.config_service import config_service
    await asyncio.sleep(120)
    while True:
        try:
            if config_service.get("finance_rates_auto_update", True):
                await update_rates()
        except Exception as e:
            logger.warning("Finance rates update loop failed: %s", e)
        await asyncio.sleep(UPDATE_INTERVAL_SECONDS)
