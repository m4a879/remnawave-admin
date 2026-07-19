"""Слой репутации IP — контракт провайдера + реестр + хранение токенов.

Дополняет БС-проверку (операторский DPI) другим источником: числится ли IP в
фрод/абуз-базах, помечен ли как VPN/proxy/hosting/tor. Каждый провайдер —
адаптер с методом lookup(ip) → нормализованный dict. Токен (у кого нужен)
хранится зашифрованным в bot_config `reputation_<slug>_token`.
"""
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from web.backend.core.crypto import encrypt_field, decrypt_field

logger = logging.getLogger(__name__)


class RepError(Exception):
    """Ошибка провайдера репутации (человекочитаемая)."""


class RepProvider(ABC):
    slug: str = ""
    name: str = ""
    needs_token: bool = True
    handles_domain: bool = False   # умеет ли принимать домен (не только IP)
    signup_url: str = ""

    @abstractmethod
    async def lookup(self, target: str, token: Optional[str]) -> Dict[str, Any]:
        """Вернуть НОРМАЛИЗОВАННЫЙ результат по IP/домену (см. normalized())."""
        raise NotImplementedError


_REGISTRY: Dict[str, RepProvider] = {}


def register(cls):
    _REGISTRY[cls.slug] = cls()
    return cls


def providers() -> List[RepProvider]:
    return list(_REGISTRY.values())


def get_provider(slug: str) -> Optional[RepProvider]:
    return _REGISTRY.get(slug)


def normalized(provider: str, ip: str, *, score: Optional[int] = None,
               is_proxy: Optional[bool] = None, is_vpn: Optional[bool] = None,
               is_hosting: Optional[bool] = None, is_tor: Optional[bool] = None,
               recent_abuse: Optional[bool] = None, country: Optional[str] = None,
               asn: Optional[str] = None, org: Optional[str] = None,
               blocked: Optional[bool] = None, rkn_domain: Optional[str] = None,
               blocked_subnets: Optional[List[str]] = None,
               raw: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "provider": provider, "ip": ip, "score": score,
        "is_proxy": is_proxy, "is_vpn": is_vpn, "is_hosting": is_hosting,
        "is_tor": is_tor, "recent_abuse": recent_abuse,
        "blocked": blocked, "rkn_domain": rkn_domain,
        "blocked_subnets": blocked_subnets or None,
        "country": country, "asn": asn, "org": org, "raw": raw or {},
    }


def looks_ip(s: str) -> bool:
    import ipaddress
    try:
        ipaddress.ip_address(s.strip())
        return True
    except ValueError:
        return False


# ── Токены ───────────────────────────────────────────────────────

def _token_key(slug: str) -> str:
    return f"reputation_{slug}_token"


def get_token(slug: str) -> Optional[str]:
    from shared.config_service import config_service
    enc = config_service.get(_token_key(slug), None)
    if not enc:
        return None
    try:
        return decrypt_field(str(enc))
    except Exception:  # noqa: BLE001
        logger.warning("reputation: токен %s не расшифровался", slug)
        return None


def is_configured(slug: str) -> bool:
    prov = get_provider(slug)
    if not prov:
        return False
    return (not prov.needs_token) or bool(get_token(slug))


async def save_token(slug: str, token: str) -> None:
    await _write_value(_token_key(slug), encrypt_field(token.strip()))


async def clear_token(slug: str) -> None:
    await _write_value(_token_key(slug), "")


async def _write_value(key: str, value: str) -> None:
    from shared.database import db_service
    from shared.db_query import update_sql
    from shared.db_schema import BOT_CONFIG_TABLE
    from shared.config_service import config_service

    if not db_service.is_connected:
        raise RepError("База данных недоступна")
    async with db_service.acquire() as conn:
        await conn.execute(
            update_sql(BOT_CONFIG_TABLE, "value = $2, updated_at = NOW()", "key = $1"),
            key, value,
        )
    try:
        if key in config_service._cache:
            config_service._cache[key].value = value
    except Exception as e:  # noqa: BLE001
        logger.debug("reputation: cache update skipped: %s", e)


# ── Проверка ─────────────────────────────────────────────────────

async def lookup_all(target: str) -> List[Dict[str, Any]]:
    """Прогнать IP/домен через всех НАСТРОЕННЫХ провайдеров.

    Домен — только через провайдеров с handles_domain (остальные умеют лишь IP).
    """
    target = target.strip()
    is_ip = looks_ip(target)
    out: List[Dict[str, Any]] = []
    for slug, prov in _REGISTRY.items():
        if not is_ip and not prov.handles_domain:
            continue
        if prov.needs_token and not get_token(slug):
            continue
        try:
            out.append(await prov.lookup(target, get_token(slug)))
        except RepError as e:
            out.append({"provider": slug, "ip": target, "error": str(e)})
        except Exception as e:  # noqa: BLE001
            logger.warning("reputation %s(%s): %s", slug, target, e)
            out.append({"provider": slug, "ip": target, "error": str(e)})
    return out
