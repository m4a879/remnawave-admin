from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row
from src.utils.auth import BotAdmin


def asn_sync_menu_keyboard(admin: BotAdmin | None = None) -> InlineKeyboardMarkup:
    rows = []
    if admin is None or admin.has_perm_sync("settings", "edit"):
        rows.append([InlineKeyboardButton(text=_("asn_sync.full_sync"), callback_data="asn_sync:full")])
        rows.append([InlineKeyboardButton(text=_("asn_sync.limit_100"), callback_data="asn_sync:limit:100")])
        rows.append([InlineKeyboardButton(text=_("asn_sync.limit_500"), callback_data="asn_sync:limit:500")])
        rows.append([InlineKeyboardButton(text=_("asn_sync.limit_1000"), callback_data="asn_sync:limit:1000")])
        rows.append([InlineKeyboardButton(text=_("asn_sync.custom_limit"), callback_data="asn_sync:custom")])
    rows.append([InlineKeyboardButton(text=_("asn_sync.status"), callback_data="asn_sync:status")])
    rows.append(nav_row(NavTarget.SYSTEM_MENU))
    return InlineKeyboardMarkup(inline_keyboard=rows)
