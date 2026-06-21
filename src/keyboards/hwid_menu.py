from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row
from src.utils.auth import BotAdmin
from src.keyboards import perm_btn


def hwid_management_keyboard(user_uuid: str, back_to: str = NavTarget.USERS_MENU, admin: BotAdmin | None = None) -> InlineKeyboardMarkup:
    """Клавиатура для меню управления HWID."""
    rows = [
        [perm_btn(admin, "users", "edit", _("user.edit_hwid"), f"uef:hwid::{user_uuid}")],
        [perm_btn(admin, "users", "edit", _("user.hwid_devices"), f"user_hwid:{user_uuid}")],
        nav_row(back_to),
    ]
    rows = [[b for b in row if b is not None] for row in rows]
    rows = [row for row in rows if row]
    return InlineKeyboardMarkup(inline_keyboard=rows)
