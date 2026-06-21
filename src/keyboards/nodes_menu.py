from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row
from src.utils.auth import BotAdmin


def nodes_list_keyboard(admin: BotAdmin | None = None) -> InlineKeyboardMarkup:
    rows = []
    if admin is None or admin.has_perm_sync("nodes", "view"):
        rows.append([InlineKeyboardButton(text=_("node.list"), callback_data="nodes:list")])
    if admin is None or admin.has_perm_sync("nodes", "create"):
        rows.append([InlineKeyboardButton(text=_("node.create"), callback_data="nodes:create")])
    if admin is None or admin.has_perm_sync("nodes", "edit"):
        rows.append([InlineKeyboardButton(text=_("node.update"), callback_data="nodes:update")])
    rows.append([InlineKeyboardButton(text=_("actions.refresh"), callback_data="nodes:refresh")])
    rows.append(nav_row(NavTarget.NODES_MENU))
    return InlineKeyboardMarkup(inline_keyboard=rows)
