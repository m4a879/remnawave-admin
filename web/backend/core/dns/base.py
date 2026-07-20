"""Мульти-провайдерное управление DNS из админки.

Провайдер = класс с CRUD над DNS-записями зон конкретного хостинга (Cloudflare,
Timeweb Cloud, reg.ru). Креды каждого провайдера хранятся ОТДЕЛЬНО, зашифрованными
(Fernet) в bot_config под ключом `dns_creds_<slug>` (JSON), правятся только через
DNS API, не через общий /settings.
"""
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Type

from web.backend.core.crypto import encrypt_field, decrypt_field

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 20.0


class DnsProviderError(Exception):
    """Ошибка DNS-провайдера с человекочитаемым сообщением (в API/UI)."""


@dataclass
class DnsField:
    """Поле формы подключения провайдера (динамический рендер на фронте)."""
    name: str
    label: str
    type: str = "text"           # text | password
    required: bool = True
    help: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "label": self.label, "type": self.type,
                "required": self.required, "help": self.help}


@dataclass
class DnsZone:
    id: str                       # провайдер-специфичный (CF zone id / fqdn / dname)
    name: str

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "name": self.name}


@dataclass
class DnsRecord:
    id: str                       # провайдер-специфичный (CF id / TW id / синтетика reg.ru)
    type: str
    name: str
    content: str
    ttl: Optional[int] = None
    proxied: Optional[bool] = None
    priority: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "type": self.type, "name": self.name,
                "content": self.content, "ttl": self.ttl,
                "proxied": self.proxied, "priority": self.priority}


class DnsProvider:
    """Контракт DNS-провайдера. Все методы принимают распакованные creds (dict)."""

    slug: str = ""
    title: str = ""
    fields: List[DnsField] = []
    record_types: List[str] = ["A", "AAAA", "CNAME", "TXT", "MX"]
    proxyable: List[str] = []     # типы с проксированием (оранжевое облако) — только CF
    supports_ttl: bool = True     # можно ли задавать TTL записи

    async def verify(self, creds: Dict[str, str]) -> bool:
        raise NotImplementedError

    async def list_zones(self, creds: Dict[str, str]) -> List[DnsZone]:
        raise NotImplementedError

    async def list_records(self, creds: Dict[str, str], zone_id: str) -> List[DnsRecord]:
        raise NotImplementedError

    async def create_record(self, creds: Dict[str, str], zone_id: str,
                            rec: Dict[str, Any]) -> DnsRecord:
        raise NotImplementedError

    async def update_record(self, creds: Dict[str, str], zone_id: str, record_id: str,
                            rec: Dict[str, Any]) -> DnsRecord:
        raise NotImplementedError

    async def delete_record(self, creds: Dict[str, str], zone_id: str, record_id: str) -> None:
        raise NotImplementedError

    @classmethod
    def to_meta(cls, configured: bool) -> Dict[str, Any]:
        return {
            "slug": cls.slug, "title": cls.title,
            "fields": [f.to_dict() for f in cls.fields],
            "record_types": cls.record_types, "proxyable": cls.proxyable,
            "supports_ttl": cls.supports_ttl, "configured": configured,
        }

    def validate_creds(self, creds: Dict[str, str]) -> None:
        for f in self.fields:
            if f.required and not (creds.get(f.name) or "").strip():
                raise DnsProviderError(f"Не заполнено поле «{f.label}»")


# ── Реестр ───────────────────────────────────────────────────────

_REGISTRY: Dict[str, Type[DnsProvider]] = {}


def register_provider(cls: Type[DnsProvider]) -> Type[DnsProvider]:
    if not cls.slug:
        raise ValueError(f"DNS provider {cls.__name__} has empty slug")
    _REGISTRY[cls.slug] = cls
    return cls


def get_provider(slug: str) -> DnsProvider:
    cls = _REGISTRY.get(slug)
    if not cls:
        raise DnsProviderError(f"Неизвестный DNS-провайдер: {slug}")
    return cls()


def list_providers() -> List[Type[DnsProvider]]:
    return sorted(_REGISTRY.values(), key=lambda c: c.title)


# ── Хранение кредов (по провайдеру, зашифровано) ─────────────────

def _creds_key(slug: str) -> str:
    return f"dns_creds_{slug}"


def get_creds(slug: str) -> Optional[Dict[str, str]]:
    from shared.config_service import config_service
    enc = config_service.get(_creds_key(slug), None)
    if not enc:
        return None
    try:
        data = json.loads(decrypt_field(str(enc)))
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001 — битый шифртекст/JSON = не настроено
        logger.warning("DNS: креды %s не расшифровались", slug)
        return None


def is_configured(slug: str) -> bool:
    return get_creds(slug) is not None


async def save_creds(slug: str, creds: Dict[str, str]) -> None:
    await _write_value(slug, encrypt_field(json.dumps(creds)))


async def clear_creds(slug: str) -> None:
    await _write_value(slug, "")


async def _write_value(slug: str, value: str) -> None:
    from shared.database import db_service
    from shared.db_query import update_sql
    from shared.db_schema import BOT_CONFIG_TABLE
    from shared.config_service import config_service

    if not db_service.is_connected:
        raise DnsProviderError("База данных недоступна")
    key = _creds_key(slug)
    async with db_service.acquire() as conn:
        await conn.execute(
            update_sql(BOT_CONFIG_TABLE, "value = $2, updated_at = NOW()", "key = $1"),
            key, value,
        )
    try:
        if key in config_service._cache:
            config_service._cache[key].value = value
    except Exception as e:  # noqa: BLE001
        logger.debug("DNS: cache update skipped (%s): %s", key, e)
