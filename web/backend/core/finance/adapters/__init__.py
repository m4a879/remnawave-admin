"""Адаптеры клиентских API хостеров для автосинка финансового модуля.

Каждый адаптер знает, как от имени клиента хостинга получить баланс аккаунта
и список услуг с датами списаний. Реестр отдаёт метаданные полей — фронт
рисует форму подключения динамически.
"""
from web.backend.core.finance.adapters.base import (
    AdapterError,
    AdapterField,
    HosterAdapter,
    Service,
    SyncResult,
    get_adapter,
    list_adapters,
    register_adapter,
)

# Регистрация конкретных адаптеров (импорт = регистрация)
from web.backend.core.finance.adapters import billmanager  # noqa: F401
from web.backend.core.finance.adapters import hostkey  # noqa: F401

__all__ = [
    "AdapterError",
    "AdapterField",
    "HosterAdapter",
    "Service",
    "SyncResult",
    "get_adapter",
    "list_adapters",
    "register_adapter",
]
