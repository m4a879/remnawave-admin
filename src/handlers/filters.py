"""Обработчики для фильтров списков."""
from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.i18n import gettext as _

from src.handlers.common import _get_target_user_id, _not_admin, _send_clean_message
from src.handlers.state import (
    HOSTS_FILTER_BY_USER,
    NODES_FILTER_BY_USER,
    SUBS_FILTER_BY_USER,
)
from src.keyboards.filters import (
    hosts_filter_keyboard,
    nodes_filter_keyboard,
    nodes_tag_filter_keyboard,
    users_filter_keyboard,
)
from src.keyboards.navigation import NavTarget
from src.utils.auth import BotAdmin
from shared.internal_api import ApiClientError, internal_api_client
from shared.logger import logger

router = Router(name="filters")


# ========================
# ФИЛЬТРЫ ПОЛЬЗОВАТЕЛЕЙ
# ========================

@router.callback_query(F.data == "filter:users:show")
async def cb_filter_users_show(callback: CallbackQuery, admin: BotAdmin) -> None:
    """Показать меню фильтров пользователей."""
    if await _not_admin(callback):
        return
    await callback.answer()
    
    user_id = _get_target_user_id(callback)
    current_filter = SUBS_FILTER_BY_USER.get(user_id) if user_id else None
    
    text = _("filter.title_users")
    if current_filter:
        filter_label = _("filter.users." + current_filter)
        text = f"{text}\n\n{_('filter.current_filter').format(filter=filter_label)}"
    else:
        text = f"{text}\n\n{_('filter.no_filter')}"
    
    keyboard = users_filter_keyboard(current_filter)
    await _send_clean_message(callback, text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("filter:users:"))
async def cb_filter_users_apply(callback: CallbackQuery, admin: BotAdmin) -> None:
    """Применить фильтр пользователей."""
    if await _not_admin(callback):
        return
    await callback.answer()
    
    user_id = _get_target_user_id(callback)
    if user_id is None:
        return
    
    parts = callback.data.split(":")
    if len(parts) < 3:
        return
    
    filter_value = parts[2]
    
    if filter_value == "show":
        # Уже обработано выше
        return
    elif filter_value == "clear":
        # Сбросить фильтр
        SUBS_FILTER_BY_USER.pop(user_id, None)
    else:
        # Применить фильтр
        SUBS_FILTER_BY_USER[user_id] = filter_value
    
    # Сбрасываем страницу на первую
    from src.handlers.state import SUBS_PAGE_BY_USER
    SUBS_PAGE_BY_USER[user_id] = 0
    
    # Переходим к списку подписок
    from src.handlers.navigation import _send_subscriptions_page
    await _send_subscriptions_page(callback, page=0)


# ========================
# ФИЛЬТРЫ НОД
# ========================

@router.callback_query(F.data == "filter:nodes:show")
async def cb_filter_nodes_show(callback: CallbackQuery, admin: BotAdmin) -> None:
    """Показать меню фильтров нод."""
    if await _not_admin(callback):
        return
    await callback.answer()
    
    user_id = _get_target_user_id(callback)
    current_filter = NODES_FILTER_BY_USER.get(user_id) if user_id else None
    
    text = _("filter.title_nodes")
    if current_filter:
        if current_filter.get("status"):
            filter_label = _("filter.nodes." + current_filter["status"])
        elif current_filter.get("tag"):
            filter_label = f"🏷 {current_filter['tag']}"
        else:
            filter_label = "—"
        text = f"{text}\n\n{_('filter.current_filter').format(filter=filter_label)}"
    else:
        text = f"{text}\n\n{_('filter.no_filter')}"
    
    keyboard = nodes_filter_keyboard(current_filter)
    await _send_clean_message(callback, text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("filter:nodes:status:"))
async def cb_filter_nodes_status(callback: CallbackQuery, admin: BotAdmin) -> None:
    """Применить фильтр нод по статусу."""
    if await _not_admin(callback):
        return
    await callback.answer()
    
    user_id = _get_target_user_id(callback)
    if user_id is None:
        return
    
    parts = callback.data.split(":")
    if len(parts) < 4:
        return
    
    status_value = parts[3]
    
    # Применить фильтр по статусу
    NODES_FILTER_BY_USER[user_id] = {"status": status_value, "tag": None}
    
    # Сбрасываем страницу на первую
    from src.handlers.state import NODES_PAGE_BY_USER
    NODES_PAGE_BY_USER[user_id] = 0
    
    # Переходим к списку нод
    from src.handlers.nodes import _fetch_nodes_with_keyboard
    text, keyboard = await _fetch_nodes_with_keyboard(user_id=user_id, page=0)
    await _send_clean_message(callback, text, reply_markup=keyboard)


@router.callback_query(F.data == "filter:nodes:tag:select")
async def cb_filter_nodes_tag_select(callback: CallbackQuery, admin: BotAdmin) -> None:
    """Показать список тегов для фильтрации нод."""
    if await _not_admin(callback):
        return
    await callback.answer()
    
    user_id = _get_target_user_id(callback)
    current_filter = NODES_FILTER_BY_USER.get(user_id) if user_id else None
    current_tag = current_filter.get("tag") if current_filter else None
    
    try:
        # Получаем все ноды для сбора тегов
        data = await internal_api_client.get_nodes()
        nodes = data.get("response", [])
        
        # Собираем все теги
        all_tags = []
        for node in nodes:
            tags = node.get("tags", [])
            if tags:
                all_tags.extend(tags)
        
        if not all_tags:
            await _send_clean_message(callback, _("filter.no_tags"), reply_markup=nodes_filter_keyboard(current_filter))
            return
        
        keyboard = nodes_tag_filter_keyboard(all_tags, current_tag)
        await _send_clean_message(callback, _("filter.tag_select"), reply_markup=keyboard)
    except ApiClientError:
        logger.exception("Failed to fetch nodes for tags")
        await _send_clean_message(callback, _("errors.generic"), reply_markup=nodes_filter_keyboard(current_filter))


@router.callback_query(F.data.startswith("filter:nodes:tag:"))
async def cb_filter_nodes_tag_apply(callback: CallbackQuery, admin: BotAdmin) -> None:
    """Применить фильтр нод по тегу."""
    if await _not_admin(callback):
        return
    await callback.answer()
    
    user_id = _get_target_user_id(callback)
    if user_id is None:
        return
    
    parts = callback.data.split(":")
    if len(parts) < 4:
        return
    
    tag_value = parts[3]
    
    if tag_value == "select":
        # Уже обработано выше
        return
    
    # Применить фильтр по тегу
    NODES_FILTER_BY_USER[user_id] = {"status": None, "tag": tag_value}
    
    # Сбрасываем страницу на первую
    from src.handlers.state import NODES_PAGE_BY_USER
    NODES_PAGE_BY_USER[user_id] = 0
    
    # Переходим к списку нод
    from src.handlers.nodes import _fetch_nodes_with_keyboard
    text, keyboard = await _fetch_nodes_with_keyboard(user_id=user_id, page=0)
    await _send_clean_message(callback, text, reply_markup=keyboard)


@router.callback_query(F.data == "filter:nodes:clear")
async def cb_filter_nodes_clear(callback: CallbackQuery, admin: BotAdmin) -> None:
    """Сбросить фильтр нод."""
    if await _not_admin(callback):
        return
    await callback.answer()
    
    user_id = _get_target_user_id(callback)
    if user_id is None:
        return
    
    # Сбросить фильтр
    NODES_FILTER_BY_USER.pop(user_id, None)
    
    # Сбрасываем страницу на первую
    from src.handlers.state import NODES_PAGE_BY_USER
    NODES_PAGE_BY_USER[user_id] = 0
    
    # Переходим к списку нод
    from src.handlers.nodes import _fetch_nodes_with_keyboard
    text, keyboard = await _fetch_nodes_with_keyboard(user_id=user_id, page=0)
    await _send_clean_message(callback, text, reply_markup=keyboard)


# ========================
# ФИЛЬТРЫ ХОСТОВ
# ========================

@router.callback_query(F.data == "filter:hosts:show")
async def cb_filter_hosts_show(callback: CallbackQuery, admin: BotAdmin) -> None:
    """Показать меню фильтров хостов."""
    if await _not_admin(callback):
        return
    await callback.answer()
    
    user_id = _get_target_user_id(callback)
    current_filter = HOSTS_FILTER_BY_USER.get(user_id) if user_id else None
    
    text = _("filter.title_hosts")
    if current_filter:
        filter_label = _("filter.hosts." + current_filter)
        text = f"{text}\n\n{_('filter.current_filter').format(filter=filter_label)}"
    else:
        text = f"{text}\n\n{_('filter.no_filter')}"
    
    keyboard = hosts_filter_keyboard(current_filter)
    await _send_clean_message(callback, text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("filter:hosts:"))
async def cb_filter_hosts_apply(callback: CallbackQuery, admin: BotAdmin) -> None:
    """Применить фильтр хостов."""
    if await _not_admin(callback):
        return
    await callback.answer()
    
    user_id = _get_target_user_id(callback)
    if user_id is None:
        return
    
    parts = callback.data.split(":")
    if len(parts) < 3:
        return
    
    filter_value = parts[2]
    
    if filter_value == "show":
        # Уже обработано выше
        return
    elif filter_value == "clear":
        # Сбросить фильтр
        HOSTS_FILTER_BY_USER.pop(user_id, None)
    else:
        # Применить фильтр
        HOSTS_FILTER_BY_USER[user_id] = filter_value
    
    # Сбрасываем страницу на первую
    from src.handlers.state import HOSTS_PAGE_BY_USER
    HOSTS_PAGE_BY_USER[user_id] = 0
    
    # Переходим к списку хостов
    from src.handlers.hosts import _fetch_hosts_with_keyboard
    text, keyboard = await _fetch_hosts_with_keyboard(user_id=user_id, page=0, admin=admin)
    await _send_clean_message(callback, text, reply_markup=keyboard)
