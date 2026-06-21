from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row
from src.utils.auth import BotAdmin
from src.keyboards import perm_btn


def node_actions_keyboard(node_uuid: str, is_disabled: bool, back_to: str = NavTarget.NODES_MENU, admin: BotAdmin | None = None) -> InlineKeyboardMarkup:
    toggle_action = "enable" if is_disabled else "disable"
    toggle_text = _("node.enable") if is_disabled else _("node.disable")
    rows = []
    row1 = [b for b in [
        perm_btn(admin, "nodes", "edit", toggle_text, f"node:{node_uuid}:{toggle_action}"),
        perm_btn(admin, "nodes", "edit", _("node.restart"), f"node:{node_uuid}:restart"),
    ] if b is not None]
    if row1:
        rows.append(row1)
    row2 = [b for b in [
        perm_btn(admin, "nodes", "edit", _("node.reset_traffic"), f"node:{node_uuid}:reset"),
    ] if b is not None]
    if row2:
        rows.append(row2)
    rows.append(nav_row(back_to))
    return InlineKeyboardMarkup(inline_keyboard=rows)
