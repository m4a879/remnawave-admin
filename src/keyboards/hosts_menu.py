from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row
from src.utils.auth import BotAdmin


def hosts_menu_keyboard(admin: BotAdmin | None = None) -> InlineKeyboardMarkup:
    rows = []
    if admin is None or admin.has_perm_sync("hosts", "view"):
        rows.append([InlineKeyboardButton(text=_("host.list"), callback_data="hosts:list")])
    if admin is None or admin.has_perm_sync("hosts", "create"):
        rows.append([InlineKeyboardButton(text=_("host.create"), callback_data="hosts:create")])
    if admin is None or admin.has_perm_sync("hosts", "edit"):
        rows.append([InlineKeyboardButton(text=_("host.update"), callback_data="hosts:update")])
    rows.append(nav_row(NavTarget.NODES_MENU))
    return InlineKeyboardMarkup(inline_keyboard=rows)
