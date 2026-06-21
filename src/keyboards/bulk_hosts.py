from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row
from src.utils.auth import BotAdmin
from src.keyboards import perm_btn


def bulk_hosts_keyboard(admin: BotAdmin | None = None) -> InlineKeyboardMarkup:
    rows = [
        [perm_btn(admin, "hosts", "edit", _("bulk_hosts.template_enable_all"), "bulk:hosts:enable_all")],
        [perm_btn(admin, "hosts", "edit", _("bulk_hosts.template_disable_all"), "bulk:hosts:disable_all")],
        [perm_btn(admin, "hosts", "edit", _("bulk_hosts.template_delete_disabled"), "bulk:hosts:delete_disabled")],
        [perm_btn(admin, "hosts", "edit", _("bulk_hosts.list"), "bulk:hosts:list")],
        nav_row(NavTarget.BULK_MENU),
    ]
    rows = [[b for b in row if b is not None] for row in rows]
    rows = [row for row in rows if row]
    return InlineKeyboardMarkup(inline_keyboard=rows)
