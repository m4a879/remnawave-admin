"""
Finance accounts mixin — API-подключения хостеров и снапшоты балансов.

credentials хранится как непрозрачная шифрованная строка (Fernet-JSON),
шифрование/дешифровка — в web-слое (web.backend.core.crypto); отсюда
креды наружу не отдаются, кроме явного get_finance_account_credentials.
"""
import json
from datetime import date
from typing import Any, Dict, List, Optional

from shared.db_schema import (
    FINANCE_ACCOUNTS_TABLE, FINANCE_SNAPSHOTS_TABLE, FINANCE_PROVIDERS_TABLE,
)
from shared.db.finance import _num, _d


def _account_row(r) -> Dict[str, Any]:
    d = dict(r)
    d.pop("credentials", None)
    d["balance"] = _num(d["balance"]) if d.get("balance") is not None else None
    d["low_balance_threshold"] = (
        _num(d["low_balance_threshold"]) if d.get("low_balance_threshold") is not None else None
    )
    if isinstance(d.get("services"), str):
        try:
            d["services"] = json.loads(d["services"])
        except ValueError:
            d["services"] = None
    for k in ("last_sync_at", "last_alerted_at", "created_at", "updated_at"):
        d[k] = _d(d.get(k))
    return d


class FinanceAccountsMixin:
    # ==================== Accounts ====================

    _ACCOUNT_SELECT = f"""
        SELECT a.*, p.name AS provider_name, p.url AS provider_url
        FROM {FINANCE_ACCOUNTS_TABLE} a
        JOIN {FINANCE_PROVIDERS_TABLE} p ON p.id = a.provider_id
    """

    async def list_finance_accounts(self, auto_sync_only: bool = False) -> List[Dict[str, Any]]:
        if not self.is_connected:
            return []
        where = "WHERE a.auto_sync" if auto_sync_only else ""
        async with self.acquire() as conn:
            rows = await conn.fetch(f"{self._ACCOUNT_SELECT} {where} ORDER BY p.name")
        return [_account_row(r) for r in rows]

    async def get_finance_account(self, account_id: int) -> Optional[Dict[str, Any]]:
        if not self.is_connected:
            return None
        async with self.acquire() as conn:
            row = await conn.fetchrow(f"{self._ACCOUNT_SELECT} WHERE a.id = $1", account_id)
        return _account_row(row) if row else None

    async def get_finance_account_credentials(self, account_id: int) -> Optional[str]:
        """Шифрованная строка кредов как есть — дешифрует web-слой."""
        if not self.is_connected:
            return None
        async with self.acquire() as conn:
            return await conn.fetchval(
                f"SELECT credentials FROM {FINANCE_ACCOUNTS_TABLE} WHERE id = $1", account_id,
            )

    async def create_finance_account(
        self, provider_id: int, adapter: str, credentials: str,
        base_url: Optional[str] = None, auto_sync: bool = True,
        low_balance_threshold: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        if not self.is_connected:
            return None
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                f"""INSERT INTO {FINANCE_ACCOUNTS_TABLE}
                    (provider_id, adapter, credentials, base_url, auto_sync, low_balance_threshold)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (provider_id) DO UPDATE SET
                        adapter = EXCLUDED.adapter,
                        credentials = EXCLUDED.credentials,
                        base_url = EXCLUDED.base_url,
                        auto_sync = EXCLUDED.auto_sync,
                        low_balance_threshold = EXCLUDED.low_balance_threshold,
                        updated_at = NOW()
                    RETURNING id""",
                provider_id, adapter, credentials, base_url, auto_sync, low_balance_threshold,
            )
        return await self.get_finance_account(row["id"]) if row else None

    async def update_finance_account(self, account_id: int, **fields) -> Optional[Dict[str, Any]]:
        if not self.is_connected:
            return None
        allowed_keys = (
            "credentials", "base_url", "auto_sync", "low_balance_threshold", "last_alerted_at",
        )
        allowed = {k: v for k, v in fields.items() if k in allowed_keys}
        if not allowed:
            return await self.get_finance_account(account_id)
        sets = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(allowed))
        async with self.acquire() as conn:
            await conn.execute(
                f"UPDATE {FINANCE_ACCOUNTS_TABLE} SET {sets}, updated_at = NOW() WHERE id = $1",
                account_id, *allowed.values(),
            )
        return await self.get_finance_account(account_id)

    async def delete_finance_account(self, account_id: int) -> bool:
        if not self.is_connected:
            return False
        async with self.acquire() as conn:
            result = await conn.execute(
                f"DELETE FROM {FINANCE_ACCOUNTS_TABLE} WHERE id = $1", account_id,
            )
        return "DELETE 1" in result

    async def set_finance_account_sync_result(
        self, account_id: int, ok: bool, error: Optional[str] = None,
        balance: Optional[float] = None, currency: Optional[str] = None,
        services: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Итог синка: статус всегда, баланс/услуги — только при успехе."""
        if not self.is_connected:
            return
        async with self.acquire() as conn:
            if ok:
                await conn.execute(
                    f"""UPDATE {FINANCE_ACCOUNTS_TABLE}
                        SET last_sync_at = NOW(), last_sync_status = 'ok', last_sync_error = NULL,
                            balance = COALESCE($2, balance),
                            balance_currency = COALESCE($3, balance_currency),
                            services = COALESCE($4::jsonb, services),
                            updated_at = NOW()
                        WHERE id = $1""",
                    account_id, balance, currency,
                    json.dumps(services, ensure_ascii=False) if services is not None else None,
                )
            else:
                await conn.execute(
                    f"""UPDATE {FINANCE_ACCOUNTS_TABLE}
                        SET last_sync_at = NOW(), last_sync_status = 'error',
                            last_sync_error = $2, updated_at = NOW()
                        WHERE id = $1""",
                    account_id, (error or "unknown")[:1000],
                )

    # ==================== Snapshots ====================

    async def record_finance_balance_snapshot(
        self, account_id: int, balance: float, currency: str,
        snapshot_date: Optional[date] = None,
    ) -> None:
        """Один снапшот на аккаунт в день; повтор в тот же день обновляет."""
        if not self.is_connected:
            return
        async with self.acquire() as conn:
            await conn.execute(
                f"""INSERT INTO {FINANCE_SNAPSHOTS_TABLE} (account_id, snapshot_date, balance, currency)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (account_id, snapshot_date) DO UPDATE
                    SET balance = EXCLUDED.balance, currency = EXCLUDED.currency""",
                account_id, snapshot_date or date.today(), round(float(balance), 2), currency.upper(),
            )

    async def list_finance_balance_snapshots(
        self, days: int = 90, account_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        if not self.is_connected:
            return []
        where = "WHERE s.snapshot_date >= CURRENT_DATE - $1::int"
        params: List[Any] = [days]
        if account_id:
            params.append(account_id)
            where += f" AND s.account_id = ${len(params)}"
        async with self.acquire() as conn:
            rows = await conn.fetch(
                f"""SELECT s.account_id, s.snapshot_date, s.balance, s.currency,
                           p.name AS provider_name
                    FROM {FINANCE_SNAPSHOTS_TABLE} s
                    JOIN {FINANCE_ACCOUNTS_TABLE} a ON a.id = s.account_id
                    JOIN {FINANCE_PROVIDERS_TABLE} p ON p.id = a.provider_id
                    {where}
                    ORDER BY s.snapshot_date, p.name""",
                *params,
            )
        return [
            dict(r) | {"balance": _num(r["balance"]), "snapshot_date": _d(r["snapshot_date"])}
            for r in rows
        ]
