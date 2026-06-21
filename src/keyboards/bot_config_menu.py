from typing import List

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row
from src.utils.auth import BotAdmin
from shared.config_service import ConfigCategory, ConfigItem


CATEGORY_EMOJI = {
    ConfigCategory.GENERAL.value: "🔧",
    ConfigCategory.NOTIFICATIONS.value: "🔔",
    ConfigCategory.SYNC.value: "🔄",
    ConfigCategory.REPORTS.value: "📊",
}


def bot_config_menu_keyboard(admin: BotAdmin | None = None) -> InlineKeyboardMarkup:
    rows = []
    if admin is None or admin.has_perm_sync("settings", "view"):
        rows.append([InlineKeyboardButton(text=_("bot_config.categories"), callback_data="bot_config:categories")])
    if admin is None or admin.has_perm_sync("settings", "view"):
        rows.append([InlineKeyboardButton(text=_("bot_config.all_settings"), callback_data="bot_config:all")])
    rows.append(nav_row(NavTarget.SYSTEM_MENU))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def bot_config_categories_keyboard(categories: List[str]) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []

    category_names = {
        "general": _("bot_config.cat_general"),
        "notifications": _("bot_config.cat_notifications"),
        "sync": _("bot_config.cat_sync"),
        "reports": _("bot_config.cat_reports"),
    }

    for cat in categories:
        emoji = CATEGORY_EMOJI.get(cat, "📁")
        name = category_names.get(cat, cat.title())
        rows.append([InlineKeyboardButton(text=f"{emoji} {name}", callback_data=f"bot_config:cat:{cat}")])

    rows.append([InlineKeyboardButton(text=_("actions.back"), callback_data="bot_config:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def bot_config_category_items_keyboard(
    category: str,
    items: List[ConfigItem],
    page: int = 0,
    page_size: int = 8,
) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []

    total_items = len(items)
    total_pages = (total_items + page_size - 1) // page_size
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, total_items)
    page_items = items[start_idx:end_idx]

    for item in page_items:
        if item.env_var_name:
            import os
            env_val = os.getenv(item.env_var_name)
            if env_val:
                status_emoji = "🔒"
            elif item.value:
                status_emoji = "✅"
            else:
                status_emoji = "⚪"
        elif item.value:
            status_emoji = "✅"
        else:
            status_emoji = "⚪"

        display_name = item.display_name or item.key
        rows.append([InlineKeyboardButton(text=f"{status_emoji} {display_name}", callback_data=f"bot_config:item:{item.key}")])

    if total_pages > 1:
        pagination_row = []
        if page > 0:
            pagination_row.append(InlineKeyboardButton(text="◀️", callback_data=f"bot_config:cat:{category}:page:{page - 1}"))
        pagination_row.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            pagination_row.append(InlineKeyboardButton(text="▶️", callback_data=f"bot_config:cat:{category}:page:{page + 1}"))
        rows.append(pagination_row)

    rows.append([InlineKeyboardButton(text=_("actions.back"), callback_data="bot_config:categories")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def bot_config_item_keyboard(item: ConfigItem) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []

    if item.options:
        for option in item.options[:6]:
            rows.append([InlineKeyboardButton(text=f"📌 {option}", callback_data=f"bot_config:set:{item.key}:{option}")])
    elif item.value_type.value == "bool":
        rows.append([
            InlineKeyboardButton(text=_("actions.enable"), callback_data=f"bot_config:set:{item.key}:true"),
            InlineKeyboardButton(text=_("actions.disable"), callback_data=f"bot_config:set:{item.key}:false"),
        ])
    else:
        rows.append([InlineKeyboardButton(text=_("bot_config.enter_value"), callback_data=f"bot_config:input:{item.key}")])

    if item.default_value:
        rows.append([InlineKeyboardButton(text=_("bot_config.reset_default"), callback_data=f"bot_config:reset:{item.key}")])

    rows.append([InlineKeyboardButton(text=_("actions.back"), callback_data=f"bot_config:cat:{item.category.value}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def bot_config_confirm_keyboard(key: str, action: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text=_("actions.yes"), callback_data=f"bot_config:confirm:{action}:{key}"),
            InlineKeyboardButton(text=_("actions.no"), callback_data=f"bot_config:item:{key}"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
