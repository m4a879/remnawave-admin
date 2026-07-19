"""bschekbot (bsbord) API — проверка нод через операторов РФ (БС/ТСПУ).

Показывает, проходит ли IP ноды через операторский DPI/белые списки — то, чего
не видно с датацентрового IP. База: https://bsbord.com/v1, Bearer bsk_live_…

Платные POST (probe) требуют Idempotency-Key. `*/preview` и GET — бесплатны и не
троттлятся. Токен хранится зашифрованным (Fernet) в bot_config, правится только
через API. Единица цены — кредит (1 кредит = 1 копейка).
"""
import logging
import uuid
from typing import Any, Dict, List, Optional

import httpx

from web.backend.core.crypto import encrypt_field, decrypt_field

logger = logging.getLogger(__name__)

BS_BASE = "https://bsbord.com/v1"
_TOKEN_KEY = "bscheck_token"
_PROBE_TIMEOUT = 130.0   # probe синхронный, до ~120с под очередью
_FAST_TIMEOUT = 25.0     # GET / preview


class BscheckError(Exception):
    """Ошибка bschekbot с человекочитаемым сообщением (в API/UI)."""


# ── Токен ────────────────────────────────────────────────────────

def _stored_token() -> Optional[str]:
    from shared.config_service import config_service
    enc = config_service.get(_TOKEN_KEY, None)
    if not enc:
        return None
    try:
        return decrypt_field(str(enc))
    except Exception:  # noqa: BLE001
        logger.warning("bscheck: токен не расшифровался")
        return None


def is_configured() -> bool:
    return _stored_token() is not None


async def save_token(token: str) -> None:
    await _write_value(encrypt_field(token.strip()))


async def clear_token() -> None:
    await _write_value("")


async def _write_value(value: str) -> None:
    from shared.database import db_service
    from shared.db_query import update_sql
    from shared.db_schema import BOT_CONFIG_TABLE
    from shared.config_service import config_service

    if not db_service.is_connected:
        raise BscheckError("База данных недоступна")
    async with db_service.acquire() as conn:
        await conn.execute(
            update_sql(BOT_CONFIG_TABLE, "value = $2, updated_at = NOW()", "key = $1"),
            _TOKEN_KEY, value,
        )
    try:
        if _TOKEN_KEY in config_service._cache:
            config_service._cache[_TOKEN_KEY].value = value
    except Exception as e:  # noqa: BLE001
        logger.debug("bscheck: cache update skipped: %s", e)


# ── Расписание авто-проверки ─────────────────────────────────────

_SCHEDULE_KEYS = (
    "bscheck_auto_enabled", "bscheck_auto_interval_hours", "bscheck_auto_dpi",
    "bscheck_auto_operators", "bscheck_auto_nodes", "bscheck_auto_budget_daily",
    "bscheck_auto_alert",
)


def _cfg_str(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, list):
        return ",".join(str(x).strip() for x in v if str(x).strip())
    return str(v)


def read_schedule() -> Dict[str, Any]:
    """Текущее расписание авто-проверки из конфигов (типизированно для API/лупа)."""
    from shared.config_service import config_service
    g = config_service.get

    def _b(k: str, d: bool) -> bool:
        return str(g(k, d)).strip().lower() in ("true", "1", "yes", "on")

    def _csv(k: str) -> List[str]:
        return [s.strip() for s in str(g(k, "") or "").split(",") if s.strip()]

    return {
        "enabled": _b("bscheck_auto_enabled", False),
        "interval_hours": int(g("bscheck_auto_interval_hours", 6) or 0),
        "dpi": str(g("bscheck_auto_dpi", "on") or "on"),
        "operators": _csv("bscheck_auto_operators"),
        "nodes": _csv("bscheck_auto_nodes"),
        "budget_daily": int(g("bscheck_auto_budget_daily", 0) or 0),
        "alert": _b("bscheck_auto_alert", True),
    }


async def save_schedule(values: Dict[str, Any]) -> None:
    """Записать ключи расписания в bot_config (только из белого списка) + кэш."""
    from shared.database import db_service
    from shared.db_query import update_sql
    from shared.db_schema import BOT_CONFIG_TABLE
    from shared.config_service import config_service
    if not db_service.is_connected:
        raise BscheckError("База данных недоступна")
    async with db_service.acquire() as conn:
        for k, v in values.items():
            if k not in _SCHEDULE_KEYS:
                continue
            sval = _cfg_str(v)
            await conn.execute(
                update_sql(BOT_CONFIG_TABLE, "value = $2, updated_at = NOW()", "key = $1"), k, sval)
            try:
                if k in config_service._cache:
                    config_service._cache[k].value = sval
            except Exception:  # noqa: BLE001
                pass


# ── HTTP ─────────────────────────────────────────────────────────

async def _request(method: str, path: str, *, token: Optional[str] = None,
                   json_body: Optional[Dict[str, Any]] = None, idempotency: bool = False,
                   timeout: float = _FAST_TIMEOUT) -> Any:
    tok = token or _stored_token()
    if not tok:
        raise BscheckError("Токен bschekbot не настроен")
    headers = {"Authorization": f"Bearer {tok}"}
    if idempotency:
        headers["Idempotency-Key"] = str(uuid.uuid4())
    try:
        async with httpx.AsyncClient(timeout=timeout, headers=headers,
                                     follow_redirects=True) as client:
            resp = await client.request(method, f"{BS_BASE}{path}", json=json_body)
    except httpx.HTTPError as e:
        raise BscheckError(f"Сеть/HTTP: {e}")
    if resp.status_code == 401:
        raise BscheckError("Токен bschekbot отклонён")
    try:
        data = resp.json()
    except ValueError:
        raise BscheckError(f"Некорректный ответ bschekbot (HTTP {resp.status_code})")
    # единый конверт ошибки {error:{code,message,details}}
    if isinstance(data, dict) and isinstance(data.get("error"), dict):
        err = data["error"]
        raise BscheckError(str(err.get("message") or err.get("code") or f"HTTP {resp.status_code}"))
    if resp.status_code >= 400:
        raise BscheckError(f"bschekbot HTTP {resp.status_code}")
    return data


async def verify_token(token: str) -> bool:
    try:
        await _request("GET", "/account", token=token)
    except BscheckError:
        return False
    return True


async def get_account() -> Dict[str, Any]:
    """Баланс/тариф аккаунта bsbord."""
    data = await _request("GET", "/account")
    return data if isinstance(data, dict) else {}


async def get_operators() -> List[Dict[str, Any]]:
    """Операторы/регионы + channel_state (DPI_ON = белый список включён)."""
    data = await _request("GET", "/operators")
    ops = data.get("operators") if isinstance(data, dict) else None
    return [o for o in (ops or []) if isinstance(o, dict)]


async def probe_preview(body: Dict[str, Any]) -> Dict[str, Any]:
    """Цена пробы без списания."""
    data = await _request("POST", "/probe/preview", json_body=body)
    return data if isinstance(data, dict) else {}


async def probe(body: Dict[str, Any]) -> Dict[str, Any]:
    """Синхронная проба целей через операторов (платно, списывает кредиты)."""
    data = await _request("POST", "/probe", json_body=body,
                          idempotency=True, timeout=_PROBE_TIMEOUT)
    return data if isinstance(data, dict) else {}


# ── Скан /24 и VLESS-тест (асинхронные: submit -> poll) ───────────

async def scans_preview(body: Dict[str, Any]) -> Dict[str, Any]:
    """Цена скана /24 без списания."""
    data = await _request("POST", "/scans/preview", json_body=body)
    return data if isinstance(data, dict) else {}


async def scans_submit(body: Dict[str, Any]) -> Dict[str, Any]:
    """Запустить скан /24 (async → scan_id). Платно (Idempotency-Key)."""
    data = await _request("POST", "/scans", json_body=body, idempotency=True, timeout=30)
    return data if isinstance(data, dict) else {}


async def scans_status(scan_id: str) -> Dict[str, Any]:
    """Статус/результат скана (поллинг, бесплатно)."""
    data = await _request("GET", f"/scans/{scan_id}")
    return data if isinstance(data, dict) else {}


async def vless_submit(body: Dict[str, Any]) -> Dict[str, Any]:
    """Запустить тест VLESS/… конфига (async → test_id). Платно."""
    data = await _request("POST", "/vless", json_body=body, idempotency=True, timeout=30)
    return data if isinstance(data, dict) else {}


async def vless_status(test_id: str) -> Dict[str, Any]:
    """Статус/результат VLESS-теста (поллинг, бесплатно; result при result_ready)."""
    data = await _request("GET", f"/vless/{test_id}")
    return data if isinstance(data, dict) else {}


# ── Разбор результата пробы для бейджа ───────────────────────────

def summarize(result: Dict[str, Any], target: str) -> Dict[str, Any]:
    """Свести ответ probe к {passed, total, operators:[{op,ok,channel_state,latency}]}.

    passed — сколько операторов пропустили трафик (ok=true), total — сколько
    реально проверено (без ушедших в skipped_dpi_off).
    """
    by_target = (result.get("by_target") or {})
    # берём запрошенную цель или единственную вернувшуюся
    node = by_target.get(target) or (next(iter(by_target.values()), {}) if by_target else {})
    by_op = (node.get("by_operator") or {}) if isinstance(node, dict) else {}
    ops: List[Dict[str, Any]] = []
    passed = 0
    for op_key, leg in by_op.items():
        if not isinstance(leg, dict):
            continue
        ok = bool(leg.get("ok"))
        if ok:
            passed += 1
        ops.append({
            "op": op_key, "ok": ok,
            "channel_state": leg.get("channel_state"),
            "latency_ms": leg.get("latency_ms"),
            "tcp_is_tls": leg.get("tcp_is_tls"),
            "error": leg.get("error") or None,
        })
    ops.sort(key=lambda o: o["op"])
    return {
        "passed": passed, "total": len(ops), "operators": ops,
        "cost_credits": result.get("cost_credits"),
        "skipped_dpi_off": [s.get("operator") for s in (result.get("skipped_dpi_off") or [])
                            if isinstance(s, dict)],
    }


def summarize_all(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Свести probe с несколькими целями: [{target, passed, total, operators}]."""
    by_target = result.get("by_target") or {}
    out: List[Dict[str, Any]] = []
    for tgt in by_target:
        s = summarize(result, tgt)
        s["target"] = tgt
        out.append(s)
    out.sort(key=lambda x: x["target"])
    return out
