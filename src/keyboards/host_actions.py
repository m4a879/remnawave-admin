from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row
from src.utils.auth import BotAdmin
from src.keyboards import perm_btn


def host_actions_keyboard(host_uuid: str, is_disabled: bool, back_to: str = NavTarget.HOSTS_MENU, admin: BotAdmin | None = None) -> InlineKeyboardMarkup:
    toggle_action = "enable" if is_disabled else "disable"
    toggle_text = _("host.enable") if is_disabled else _("host.disable")
    rows = []
    row1 = [b for b in [
        perm_btn(admin, "hosts", "edit", toggle_text, f"host:{host_uuid}:{toggle_action}"),
    ] if b is not None]
    if row1:
        rows.append(row1)
    rows.append(nav_row(back_to))
    return InlineKeyboardMarkup(inline_keyboard=rows)
