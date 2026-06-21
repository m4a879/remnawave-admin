from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row
from src.utils.auth import BotAdmin
from src.keyboards import perm_btn


def bulk_nodes_keyboard(admin: BotAdmin | None = None) -> InlineKeyboardMarkup:
    rows = [
        [perm_btn(admin, "nodes", "edit", _("bulk_nodes.profile"), "bulk:nodes:profile")],
        [perm_btn(admin, "nodes", "edit", _("bulk_nodes.enable_all"), "bulk:nodes:enable_all")],
        [perm_btn(admin, "nodes", "edit", _("bulk_nodes.disable_all"), "bulk:nodes:disable_all")],
        [perm_btn(admin, "nodes", "edit", _("bulk_nodes.restart_all"), "bulk:nodes:restart_all")],
        [perm_btn(admin, "nodes", "edit", _("bulk_nodes.reset_traffic_all"), "bulk:nodes:reset_traffic_all")],
        [perm_btn(admin, "nodes", "edit", _("bulk_nodes.assign_profile"), "bulk:nodes:assign_profile")],
        nav_row(NavTarget.BULK_MENU),
    ]
    rows = [[b for b in row if b is not None] for row in rows]
    rows = [row for row in rows if row]
    return InlineKeyboardMarkup(inline_keyboard=rows)
