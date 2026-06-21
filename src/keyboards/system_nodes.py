from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row
from src.utils.auth import BotAdmin
from src.keyboards import perm_btn


def system_nodes_keyboard(admin: BotAdmin | None = None) -> InlineKeyboardMarkup:
    rows = [
        [perm_btn(admin, "nodes", "edit", _("system_nodes.list"), "system:nodes:list")],
        nav_row(NavTarget.NODES_LIST),
    ]
    rows = [[b for b in row if b is not None] for row in rows]
    rows = [row for row in rows if row]
    return InlineKeyboardMarkup(inline_keyboard=rows)
