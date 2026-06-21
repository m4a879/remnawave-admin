from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row
from src.utils.auth import BotAdmin
from src.keyboards import perm_btn


def node_edit_keyboard(node_uuid: str, is_disabled: bool = False, back_to: str = NavTarget.NODES_LIST, admin: BotAdmin | None = None) -> InlineKeyboardMarkup:
    """Клавиатура для редактирования ноды."""
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
        perm_btn(admin, "nodes", "edit", _("node.edit_name"), f"nef:name::{node_uuid}"),
        perm_btn(admin, "nodes", "edit", _("node.edit_address"), f"nef:address::{node_uuid}"),
    ] if b is not None]
    if row2:
        rows.append(row2)
    row3 = [b for b in [
        perm_btn(admin, "nodes", "edit", _("node.edit_port"), f"nef:port::{node_uuid}"),
        perm_btn(admin, "nodes", "edit", _("node.edit_country_code"), f"nef:country_code::{node_uuid}"),
    ] if b is not None]
    if row3:
        rows.append(row3)
    row4 = [b for b in [
        perm_btn(admin, "nodes", "edit", _("node.edit_provider"), f"nef:provider::{node_uuid}"),
        perm_btn(admin, "nodes", "edit", _("node.edit_config_profile"), f"nef:config_profile::{node_uuid}"),
    ] if b is not None]
    if row4:
        rows.append(row4)
    row5 = [b for b in [
        perm_btn(admin, "nodes", "edit", _("node.edit_traffic_limit"), f"nef:traffic_limit::{node_uuid}"),
        perm_btn(admin, "nodes", "edit", _("node.edit_notify_percent"), f"nef:notify_percent::{node_uuid}"),
    ] if b is not None]
    if row5:
        rows.append(row5)
    row6 = [b for b in [
        perm_btn(admin, "nodes", "edit", _("node.edit_traffic_reset_day"), f"nef:traffic_reset_day::{node_uuid}"),
        perm_btn(admin, "nodes", "edit", _("node.edit_consumption_multiplier"), f"nef:consumption_multiplier::{node_uuid}"),
    ] if b is not None]
    if row6:
        rows.append(row6)
    row7 = [b for b in [
        perm_btn(admin, "nodes", "edit", _("node.edit_tags"), f"nef:tags::{node_uuid}"),
    ] if b is not None]
    if row7:
        rows.append(row7)
    row8 = [b for b in [
        perm_btn(admin, "nodes", "edit", _("node.agent_token"), f"node_agent_token:{node_uuid}"),
    ] if b is not None]
    if row8:
        rows.append(row8)
    row9 = [b for b in [
        perm_btn(admin, "nodes", "edit", _("node.delete"), f"node_delete:{node_uuid}"),
    ] if b is not None]
    if row9:
        rows.append(row9)
    rows.append(nav_row(back_to))
    return InlineKeyboardMarkup(inline_keyboard=rows)
