"""Finance API — собственный учёт финансов инфраструктуры (P&L).

Заменяет прокси к панельному infra-billing: категории, провайдеры, записи
расходов/доходов с валютами и циклами, платежи с фиксацией курса, курсы
валют, сводка P&L и импорт данных из панели.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from web.backend.api.deps import AdminUser, require_permission
from shared.database import db_service
from shared.config_service import config_service
from shared.db.finance import BILLING_CYCLES, ITEM_KINDS

logger = logging.getLogger(__name__)
router = APIRouter()


def _base_currency() -> str:
    return str(config_service.get("finance_base_currency", "RUB") or "RUB").upper()


async def _base_rate() -> float:
    """Курс базовой валюты к RUB (RUB -> 1.0)."""
    base = _base_currency()
    if base == "RUB":
        return 1.0
    for r in await db_service.get_finance_rates():
        if r["currency"] == base and r["rate_rub"]:
            return float(r["rate_rub"])
    return 1.0


# ── Pydantic модели ──────────────────────────────────────────────


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: str = "expense"
    color: Optional[str] = None
    icon: Optional[str] = None

    @field_validator("kind")
    @classmethod
    def _kind(cls, v):
        if v not in ITEM_KINDS:
            raise ValueError("kind must be expense|income")
        return v


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    color: Optional[str] = None
    icon: Optional[str] = None
    sort_order: Optional[int] = None


class ProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    url: Optional[str] = None
    favicon_url: Optional[str] = None
    notes: Optional[str] = None


class ProviderUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    url: Optional[str] = None
    favicon_url: Optional[str] = None
    notes: Optional[str] = None


class ItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: str = "expense"
    category_id: Optional[int] = None
    provider_id: Optional[int] = None
    node_uuid: Optional[str] = None
    currency: str = Field(default="RUB", min_length=3, max_length=8)
    amount: float = Field(default=0, ge=0)
    billing_cycle: str = "monthly"
    cycle_days: Optional[int] = Field(default=None, ge=1, le=3650)
    next_due_at: Optional[str] = None
    url: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("kind")
    @classmethod
    def _kind(cls, v):
        if v not in ITEM_KINDS:
            raise ValueError("kind must be expense|income")
        return v

    @field_validator("billing_cycle")
    @classmethod
    def _cycle(cls, v):
        if v not in BILLING_CYCLES:
            raise ValueError(f"billing_cycle must be one of {BILLING_CYCLES}")
        return v


class ItemUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    kind: Optional[str] = None
    category_id: Optional[int] = None
    provider_id: Optional[int] = None
    node_uuid: Optional[str] = None
    currency: Optional[str] = Field(default=None, min_length=3, max_length=8)
    amount: Optional[float] = Field(default=None, ge=0)
    billing_cycle: Optional[str] = None
    cycle_days: Optional[int] = Field(default=None, ge=1, le=3650)
    next_due_at: Optional[str] = None
    url: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None

    @field_validator("kind")
    @classmethod
    def _kind(cls, v):
        if v is not None and v not in ITEM_KINDS:
            raise ValueError("kind must be expense|income")
        return v

    @field_validator("billing_cycle")
    @classmethod
    def _cycle(cls, v):
        if v is not None and v not in BILLING_CYCLES:
            raise ValueError(f"billing_cycle must be one of {BILLING_CYCLES}")
        return v

    @field_validator("status")
    @classmethod
    def _status(cls, v):
        if v is not None and v not in ("active", "archived"):
            raise ValueError("status must be active|archived")
        return v


class MarkPaid(BaseModel):
    amount: Optional[float] = Field(default=None, ge=0)
    paid_at: Optional[str] = None
    comment: Optional[str] = None


class PaymentCreate(BaseModel):
    item_id: Optional[int] = None
    item_name: Optional[str] = Field(default=None, max_length=200)
    kind: str = "expense"
    paid_at: str
    amount: float = Field(gt=0)
    currency: str = Field(default="RUB", min_length=3, max_length=8)
    comment: Optional[str] = None

    @field_validator("kind")
    @classmethod
    def _kind(cls, v):
        if v not in ITEM_KINDS:
            raise ValueError("kind must be expense|income")
        return v


class RateUpdate(BaseModel):
    rate_rub: float = Field(gt=0)
    is_manual: bool = True


# ── Summary / Upcoming ───────────────────────────────────────────


@router.get("/summary")
async def finance_summary(
    months: int = Query(6, ge=1, le=36),
    admin: AdminUser = Depends(require_permission("finance", "view")),
):
    summary = await db_service.finance_summary(months=months)
    base = _base_currency()
    base_rate = await _base_rate()

    def conv(v_rub: float) -> float:
        return round(v_rub / base_rate, 2)

    return {
        "base_currency": base,
        "monthly": [
            {**m, "expense": conv(m["expense_rub"]), "income": conv(m["income_rub"]),
             "net": conv(m["net_rub"])}
            for m in summary["monthly"]
        ],
        "by_category": [
            {**c, "monthly": conv(c["monthly_rub"])} for c in summary["by_category"]
        ],
        "by_currency": summary["by_currency"],
        "recurring": {
            "expense": conv(summary["recurring"].get("expense_rub", 0)),
            "income": conv(summary["recurring"].get("income_rub", 0)),
            "net": conv(summary["recurring"].get("net_rub", 0)),
        },
    }


@router.get("/upcoming")
async def finance_upcoming(
    days: int = Query(30, ge=1, le=365),
    admin: AdminUser = Depends(require_permission("finance", "view")),
):
    items = await db_service.upcoming_finance_payments(days=days)
    return {"items": items, "total": len(items)}


# ── Categories ───────────────────────────────────────────────────


@router.get("/categories")
async def list_categories(admin: AdminUser = Depends(require_permission("finance", "view"))):
    return {"items": await db_service.list_finance_categories()}


@router.post("/categories")
async def create_category(
    data: CategoryCreate,
    admin: AdminUser = Depends(require_permission("finance", "create")),
):
    created = await db_service.create_finance_category(data.name, data.kind, data.color, data.icon)
    if not created:
        raise HTTPException(status_code=409, detail="Category already exists")
    return created


@router.patch("/categories/{category_id}")
async def update_category(
    category_id: int,
    data: CategoryUpdate,
    admin: AdminUser = Depends(require_permission("finance", "edit")),
):
    ok = await db_service.update_finance_category(
        category_id, **data.model_dump(exclude_unset=True, exclude_none=True),
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"status": "ok"}


@router.delete("/categories/{category_id}")
async def delete_category(
    category_id: int,
    admin: AdminUser = Depends(require_permission("finance", "delete")),
):
    ok = await db_service.delete_finance_category(category_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Category not found or is system")
    return {"status": "ok"}


# ── Providers ────────────────────────────────────────────────────


@router.get("/providers")
async def list_providers(admin: AdminUser = Depends(require_permission("finance", "view"))):
    return {"items": await db_service.list_finance_providers()}


@router.post("/providers")
async def create_provider(
    data: ProviderCreate,
    admin: AdminUser = Depends(require_permission("finance", "create")),
):
    created = await db_service.create_finance_provider(
        data.name, data.url, data.favicon_url, data.notes,
    )
    if not created:
        raise HTTPException(status_code=500, detail="Failed to create provider")
    return created


@router.patch("/providers/{provider_id}")
async def update_provider(
    provider_id: int,
    data: ProviderUpdate,
    admin: AdminUser = Depends(require_permission("finance", "edit")),
):
    ok = await db_service.update_finance_provider(
        provider_id, **data.model_dump(exclude_unset=True, exclude_none=True),
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Provider not found")
    return {"status": "ok"}


@router.delete("/providers/{provider_id}")
async def delete_provider(
    provider_id: int,
    admin: AdminUser = Depends(require_permission("finance", "delete")),
):
    ok = await db_service.delete_finance_provider(provider_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Provider not found")
    return {"status": "ok"}


# ── Items ────────────────────────────────────────────────────────


@router.get("/items")
async def list_items(
    kind: Optional[str] = Query(None),
    status: Optional[str] = Query("active"),
    category_id: Optional[int] = Query(None),
    currency: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    admin: AdminUser = Depends(require_permission("finance", "view")),
):
    items = await db_service.list_finance_items(
        kind=kind, status=status or None, category_id=category_id,
        currency=currency, search=search,
    )
    return {"items": items, "total": len(items)}


@router.post("/items")
async def create_item(
    data: ItemCreate,
    admin: AdminUser = Depends(require_permission("finance", "create")),
):
    item = await db_service.create_finance_item(**data.model_dump())
    if not item:
        raise HTTPException(status_code=500, detail="Failed to create item")
    return item


@router.patch("/items/{item_id}")
async def update_item(
    item_id: int,
    data: ItemUpdate,
    admin: AdminUser = Depends(require_permission("finance", "edit")),
):
    item = await db_service.update_finance_item(item_id, **data.model_dump(exclude_unset=True))
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.delete("/items/{item_id}")
async def delete_item(
    item_id: int,
    admin: AdminUser = Depends(require_permission("finance", "delete")),
):
    ok = await db_service.delete_finance_item(item_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"status": "ok"}


@router.post("/items/{item_id}/paid")
async def mark_paid(
    item_id: int,
    data: MarkPaid,
    admin: AdminUser = Depends(require_permission("finance", "edit")),
):
    item = await db_service.mark_finance_item_paid(
        item_id, amount=data.amount, paid_at=data.paid_at, comment=data.comment,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.post("/items/{item_id}/skip")
async def skip_cycle(
    item_id: int,
    admin: AdminUser = Depends(require_permission("finance", "edit")),
):
    item = await db_service.skip_finance_item_cycle(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


# ── Payments ─────────────────────────────────────────────────────


@router.get("/payments")
async def list_payments(
    item_id: Optional[int] = Query(None),
    since: Optional[str] = Query(None),
    until: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin: AdminUser = Depends(require_permission("finance", "view")),
):
    items = await db_service.list_finance_payments(
        item_id=item_id, since=since, until=until, limit=limit, offset=offset,
    )
    return {"items": items, "total": len(items)}


@router.post("/payments")
async def create_payment(
    data: PaymentCreate,
    admin: AdminUser = Depends(require_permission("finance", "create")),
):
    """Произвольный платёж/доход без привязки к записи (или с привязкой без сдвига цикла)."""
    from shared.db_schema import FINANCE_PAYMENTS_TABLE, FINANCE_RATES_TABLE
    from datetime import date as _date

    item_name = data.item_name
    if data.item_id and not item_name:
        item = await db_service.get_finance_item(data.item_id)
        item_name = (item or {}).get("name")
    if not item_name:
        item_name = "Без названия"

    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            f"""INSERT INTO {FINANCE_PAYMENTS_TABLE}
                (item_id, item_name, kind, paid_at, amount, currency, rate_rub, comment, source)
                VALUES ($1, $2, $3, $4::date, $5, $6,
                        (SELECT rate_rub FROM {FINANCE_RATES_TABLE} WHERE currency = $6),
                        $7, 'manual')
                RETURNING id""",
            data.item_id, item_name, data.kind, _date.fromisoformat(data.paid_at),
            round(data.amount, 2), data.currency.upper(), data.comment,
        )
    return {"id": row["id"], "status": "ok"}


@router.delete("/payments/{payment_id}")
async def delete_payment(
    payment_id: int,
    admin: AdminUser = Depends(require_permission("finance", "delete")),
):
    ok = await db_service.delete_finance_payment(payment_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Payment not found")
    return {"status": "ok"}


# ── Rates ────────────────────────────────────────────────────────


@router.get("/rates")
async def list_rates(admin: AdminUser = Depends(require_permission("finance", "view"))):
    return {"items": await db_service.get_finance_rates(), "base_currency": _base_currency()}


@router.put("/rates/{currency}")
async def set_rate(
    currency: str,
    data: RateUpdate,
    admin: AdminUser = Depends(require_permission("finance", "edit")),
):
    await db_service.upsert_finance_rate(currency, data.rate_rub, is_manual=data.is_manual)
    return {"status": "ok"}


@router.post("/rates/refresh")
async def refresh_rates(admin: AdminUser = Depends(require_permission("finance", "edit"))):
    from web.backend.core.finance.rates import update_rates
    updated = await update_rates()
    return {"updated": updated, "items": await db_service.get_finance_rates()}


# ── Import from panel ────────────────────────────────────────────


@router.post("/import-panel")
async def import_panel(admin: AdminUser = Depends(require_permission("finance", "create"))):
    """Одноразовый импорт провайдеров/биллинг-нод/истории из панельного infra-billing."""
    from web.backend.core.finance.importer import import_from_panel
    return await import_from_panel()
