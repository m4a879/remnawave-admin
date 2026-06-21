from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row
from src.utils.auth import BotAdmin
from src.keyboards import perm_btn


def hwid_devices_keyboard(user_uuid: str, devices: list[dict], back_to: str = NavTarget.USERS_MENU, admin: BotAdmin | None = None) -> InlineKeyboardMarkup:
    """Клавиатура для управления HWID устройствами пользователя."""
    rows: list[list[InlineKeyboardButton]] = []

    for idx, device in enumerate(devices[:10], 1):
        hwid = device.get("hwid", "n/a")
        hwid_display = hwid[:20] + "..." if len(hwid) > 20 else hwid
        rows.append([
            perm_btn(admin, "users", "edit", f"🗑 {idx}. {hwid_display}", f"hwid_delete_idx:{user_uuid}:{idx-1}")
        ])

    if devices:
        rows.append([
            perm_btn(admin, "users", "edit", _("hwid.delete_all"), f"hwid_delete_all:{user_uuid}")
        ])

    rows.append(nav_row(back_to))
    rows = [[b for b in row if b is not None] for row in rows]
    rows = [row for row in rows if row]
    return InlineKeyboardMarkup(inline_keyboard=rows)
