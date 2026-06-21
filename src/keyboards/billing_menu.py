from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row
from src.utils.auth import BotAdmin


def billing_menu_keyboard(admin: BotAdmin | None = None) -> InlineKeyboardMarkup:
    rows = []
    if admin is None or admin.has_perm_sync("billing", "view"):
        rows.append([InlineKeyboardButton(text=_("billing.stats"), callback_data="billing:stats")])
    if admin is None or admin.has_perm_sync("billing", "create"):
        rows.append([InlineKeyboardButton(text=_("billing.create"), callback_data="billing:create")])
    if admin is None or admin.has_perm_sync("billing", "delete"):
        rows.append([InlineKeyboardButton(text=_("billing.delete"), callback_data="billing:delete")])
    rows.append(nav_row(NavTarget.BILLING_OVERVIEW))
    return InlineKeyboardMarkup(inline_keyboard=rows)
