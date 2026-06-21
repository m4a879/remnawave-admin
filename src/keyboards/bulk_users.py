from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row
from src.utils.auth import BotAdmin
from src.keyboards import perm_btn


def bulk_users_keyboard(admin: BotAdmin | None = None) -> InlineKeyboardMarkup:
    rows = [
        [perm_btn(admin, "users", "bulk_operations", _("bulk.template_delete_disabled"), "bulk:users:delete:DISABLED")],
        [perm_btn(admin, "users", "bulk_operations", _("bulk.template_delete_expired"), "bulk:users:delete:EXPIRED")],
        [perm_btn(admin, "users", "bulk_operations", _("bulk.template_extend_active"), "bulk:users:extend_active")],
        [perm_btn(admin, "users", "bulk_operations", _("bulk.reset_all_traffic"), "bulk:users:reset")],
        [
            perm_btn(admin, "users", "bulk_operations", _("bulk.extend_all_7"), "bulk:users:extend_all:7"),
            perm_btn(admin, "users", "bulk_operations", _("bulk.extend_all_30"), "bulk:users:extend_all:30"),
        ],
        nav_row(NavTarget.BULK_MENU),
    ]
    rows = [[b for b in row if b is not None] for row in rows]
    rows = [row for row in rows if row]
    return InlineKeyboardMarkup(inline_keyboard=rows)
