"""Одноразовый импорт данных из панельного infra-billing Remnawave.

Переносит провайдеров, биллинг-ноды (как finance_items категории «Ноды») и
историю платежей. Идемпотентен: провайдеры апсертятся по имени, записи по
node_uuid/имени не дублируются, платежи проверяются по (имя, дата, сумма).
Суммы панели безвалютные — импортируются в базовой валюте отчётов.
"""
import logging
from datetime import datetime, date
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _parse_date(value: Optional[str]) -> Optional[str]:
    d = _parse_date_obj(value)
    return d.isoformat() if d else None


def _parse_date_obj(value: Optional[str]) -> Optional[date]:
    """ISO-строка панели -> datetime.date (для asyncpg-параметров типа date)."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        return None


async def import_from_panel() -> Dict[str, Any]:
    """Импортировать провайдеров, биллинг-ноды и историю из Panel API."""
    from shared.api_client import api_client
    from shared.database import db_service
    from shared.config_service import config_service
    from shared.db_schema import FINANCE_PAYMENTS_TABLE

    base_currency = str(config_service.get("finance_base_currency", "RUB") or "RUB").upper()
    result = {"providers": 0, "items": 0, "payments": 0, "skipped": 0, "errors": []}

    # ── Провайдеры ──
    provider_map: Dict[str, int] = {}  # panel uuid -> наш id
    try:
        resp = (await api_client.get_infra_providers(use_cache=False)).get("response", {})
        for p in (resp.get("providers") or []):
            name = p.get("name")
            if not name:
                continue
            created = await db_service.create_finance_provider(
                name=name,
                url=p.get("loginUrl"),
                favicon_url=p.get("faviconLink"),
            )
            if created:
                provider_map[p.get("uuid", "")] = created["id"]
                result["providers"] += 1
    except Exception as e:
        logger.warning("Finance import: providers failed: %s", e)
        result["errors"].append(f"providers: {e}")

    # ── Категория «Ноды» для импортированных записей ──
    nodes_category_id = None
    for cat in await db_service.list_finance_categories():
        if cat["kind"] == "expense" and cat["name"] == "Ноды":
            nodes_category_id = cat["id"]
            break

    # ── Биллинг-ноды -> finance_items ──
    existing_items = await db_service.list_finance_items(status=None)
    existing_node_uuids = {i["node_uuid"] for i in existing_items if i.get("node_uuid")}
    existing_names = {i["name"] for i in existing_items}
    try:
        resp = (await api_client.get_infra_billing_nodes(use_cache=False)).get("response", {})
        for bn in (resp.get("billingNodes") or []):
            node_uuid = bn.get("nodeUuid") or (bn.get("node") or {}).get("uuid")
            name = bn.get("name") or (bn.get("node") or {}).get("name")
            if node_uuid and not name:
                node = await db_service.get_node_by_uuid(node_uuid)
                name = (node or {}).get("name") or node_uuid[:8]
            if not name:
                continue
            if (node_uuid and node_uuid in existing_node_uuids) or (not node_uuid and name in existing_names):
                result["skipped"] += 1
                continue
            provider_uuid = bn.get("providerUuid") or (bn.get("provider") or {}).get("uuid") or ""
            await db_service.create_finance_item(
                name=name,
                kind="expense",
                category_id=nodes_category_id,
                provider_id=provider_map.get(provider_uuid),
                node_uuid=node_uuid,
                currency=base_currency,
                amount=0.0,  # панель не хранит сумму по ноде — заполняется руками
                billing_cycle="monthly",
                next_due_at=_parse_date(bn.get("nextBillingAt")),
                notes="Импорт из панельного биллинга Remnawave",
            )
            result["items"] += 1
    except Exception as e:
        logger.warning("Finance import: billing nodes failed: %s", e)
        result["errors"].append(f"nodes: {e}")

    # ── История платежей ──
    try:
        resp = (await api_client.get_infra_billing_history(use_cache=False)).get("response", {})
        async with db_service.acquire() as conn:
            for rec in (resp.get("records") or []):
                provider_name = (rec.get("provider") or {}).get("name") or "Панельный биллинг"
                amount = round(float(rec.get("amount") or 0), 2)
                paid_at = _parse_date_obj(rec.get("billedAt"))
                if not paid_at or amount <= 0:
                    result["skipped"] += 1
                    continue
                exists = await conn.fetchval(
                    f"""SELECT 1 FROM {FINANCE_PAYMENTS_TABLE}
                        WHERE item_name = $1 AND paid_at = $2 AND amount = $3""",
                    provider_name, paid_at, amount,
                )
                if exists:
                    result["skipped"] += 1
                    continue
                await conn.execute(
                    f"""INSERT INTO {FINANCE_PAYMENTS_TABLE}
                        (item_id, item_name, kind, paid_at, amount, currency, rate_rub, comment, source)
                        VALUES (NULL, $1, 'expense', $2, $3, $4,
                                (SELECT rate_rub FROM finance_rates WHERE currency = $4),
                                'Импорт из панельного биллинга', 'import')""",
                    provider_name, paid_at, amount, base_currency,
                )
                result["payments"] += 1
    except Exception as e:
        logger.warning("Finance import: history failed: %s", e)
        result["errors"].append(f"history: {e}")

    logger.info(
        "Finance import done: %d providers, %d items, %d payments, %d skipped",
        result["providers"], result["items"], result["payments"], result["skipped"],
    )
    return result
