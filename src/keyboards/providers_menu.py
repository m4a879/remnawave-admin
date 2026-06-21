from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row
from src.utils.auth import BotAdmin


def providers_menu_keyboard(admin: BotAdmin | None = None) -> InlineKeyboardMarkup:
    rows = []
    if admin is None or admin.has_perm_sync("billing", "create"):
        rows.append([InlineKeyboardButton(text=_("provider.create"), callback_data="providers:create")])
    if admin is None or admin.has_perm_sync("billing", "edit"):
        rows.append([InlineKeyboardButton(text=_("provider.update"), callback_data="providers:update")])
    if admin is None or admin.has_perm_sync("billing", "delete"):
        rows.append([InlineKeyboardButton(text=_("provider.delete"), callback_data="providers:delete")])
    rows.append(nav_row(NavTarget.BILLING_OVERVIEW))
    return InlineKeyboardMarkup(inline_keyboard=rows)
