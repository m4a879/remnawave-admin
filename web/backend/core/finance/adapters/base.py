"""База фреймворка адаптеров: контракт, реестр, общие типы.

Адаптер — stateless-класс: все данные подключения (base_url, креды) приходят
параметрами в fetch/test. Креды — словарь по описанным в adapter.fields ключам;
шифрование при хранении делает API-слой, адаптер видит открытые значения.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type

import logging

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 20.0


class AdapterError(Exception):
    """Ошибка адаптера с человекочитаемым сообщением (уходит в UI/лог синка)."""


@dataclass
class AdapterField:
    """Описание поля формы подключения (динамический рендер на фронте)."""
    name: str
    label: str
    type: str = "text"  # text | password | url
    required: bool = True
    placeholder: Optional[str] = None
    help: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name, "label": self.label, "type": self.type,
            "required": self.required, "placeholder": self.placeholder, "help": self.help,
        }


@dataclass
class Service:
    """Услуга у хостера: имя, цена за период, дата следующего списания."""
    name: str
    status: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    period: Optional[str] = None          # monthly | yearly | days:<n> | raw-строка хостера
    next_due_at: Optional[str] = None     # ISO date
    external_id: Optional[str] = None
    specs: Optional[str] = None           # краткие характеристики: CPU/RAM/диск/локация

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name, "status": self.status, "price": self.price,
            "currency": self.currency, "period": self.period,
            "next_due_at": self.next_due_at, "external_id": self.external_id,
            "specs": self.specs,
        }


@dataclass
class SyncResult:
    balance: Optional[float] = None
    currency: Optional[str] = None
    services: List[Service] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "balance": self.balance,
            "currency": self.currency,
            "services": [s.to_dict() for s in self.services],
        }


class HosterAdapter:
    """Контракт адаптера. Наследники определяют slug/title/fields и fetch()."""

    slug: str = ""
    title: str = ""
    #: подсказка в UI, какие хостеры покрывает адаптер
    description: str = ""
    #: нужен ли base_url (self-hosted биллинги типа BILLmanager) или он фиксирован
    needs_base_url: bool = True
    fields: List[AdapterField] = []

    async def fetch(self, base_url: Optional[str], credentials: Dict[str, str]) -> SyncResult:
        """Снять баланс и услуги. Кидает AdapterError с понятным текстом."""
        raise NotImplementedError

    async def test(self, base_url: Optional[str], credentials: Dict[str, str]) -> SyncResult:
        """Проверка подключения — по умолчанию тот же fetch."""
        return await self.fetch(base_url, credentials)

    def validate_credentials(self, credentials: Dict[str, str]) -> None:
        for f in self.fields:
            if f.required and not (credentials.get(f.name) or "").strip():
                raise AdapterError(f"Не заполнено поле «{f.label}»")

    @classmethod
    def to_meta(cls) -> Dict[str, Any]:
        return {
            "slug": cls.slug,
            "title": cls.title,
            "description": cls.description,
            "needs_base_url": cls.needs_base_url,
            "fields": [f.to_dict() for f in cls.fields],
        }


_REGISTRY: Dict[str, Type[HosterAdapter]] = {}


def register_adapter(cls: Type[HosterAdapter]) -> Type[HosterAdapter]:
    """Декоратор регистрации адаптера в реестре."""
    if not cls.slug:
        raise ValueError(f"Adapter {cls.__name__} has empty slug")
    _REGISTRY[cls.slug] = cls
    return cls


def get_adapter(slug: str) -> HosterAdapter:
    cls = _REGISTRY.get(slug)
    if not cls:
        raise AdapterError(f"Неизвестный адаптер: {slug}")
    return cls()


def list_adapters() -> List[Dict[str, Any]]:
    return [cls.to_meta() for cls in sorted(_REGISTRY.values(), key=lambda c: c.title)]
