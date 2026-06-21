from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row
from src.utils.auth import BotAdmin
from src.keyboards import perm_btn


def host_edit_keyboard(host_uuid: str, back_to: str = NavTarget.HOSTS_MENU, admin: BotAdmin | None = None) -> InlineKeyboardMarkup:
    """Клавиатура для редактирования хоста."""
    rows = []
    row1 = [b for b in [
        perm_btn(admin, "hosts", "edit", _("host.edit_remark"), f"hef:remark::{host_uuid}"),
        perm_btn(admin, "hosts", "edit", _("host.edit_address"), f"hef:address::{host_uuid}"),
    ] if b is not None]
    if row1:
        rows.append(row1)
    row2 = [b for b in [
        perm_btn(admin, "hosts", "edit", _("host.edit_port"), f"hef:port::{host_uuid}"),
        perm_btn(admin, "hosts", "edit", _("host.edit_tag"), f"hef:tag::{host_uuid}"),
    ] if b is not None]
    if row2:
        rows.append(row2)
    row3 = [b for b in [
        perm_btn(admin, "hosts", "edit", _("host.edit_inbound"), f"hef:inbound::{host_uuid}"),
    ] if b is not None]
    if row3:
        rows.append(row3)
    rows.append(nav_row(back_to))
    return InlineKeyboardMarkup(inline_keyboard=rows)
