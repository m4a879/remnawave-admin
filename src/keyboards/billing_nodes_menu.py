from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row
from src.utils.auth import BotAdmin


def billing_nodes_menu_keyboard(admin: BotAdmin | None = None) -> InlineKeyboardMarkup:
    rows = []
    if admin is None or admin.has_perm_sync("billing", "view"):
        rows.append([InlineKeyboardButton(text=_("billing_nodes.stats"), callback_data="billing_nodes:stats")])
    if admin is None or admin.has_perm_sync("billing", "create"):
        rows.append([InlineKeyboardButton(text=_("billing_nodes.create"), callback_data="billing_nodes:create")])
    if admin is None or admin.has_perm_sync("billing", "edit"):
        rows.append([InlineKeyboardButton(text=_("billing_nodes.update"), callback_data="billing_nodes:update")])
    if admin is None or admin.has_perm_sync("billing", "delete"):
        rows.append([InlineKeyboardButton(text=_("billing_nodes.delete"), callback_data="billing_nodes:delete")])
    rows.append(nav_row(NavTarget.BILLING_OVERVIEW))
    return InlineKeyboardMarkup(inline_keyboard=rows)
