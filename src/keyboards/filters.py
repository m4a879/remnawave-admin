from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row


def users_filter_keyboard(current_filter: str | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    filters = [
        ("ACTIVE", "filter.users.ACTIVE"),
        ("DISABLED", "filter.users.DISABLED"),
        ("LIMITED", "filter.users.LIMITED"),
        ("EXPIRED", "filter.users.EXPIRED"),
    ]

    for filter_value, label_key in filters:
        prefix = "✓ " if current_filter == filter_value else ""
        rows.append([InlineKeyboardButton(text=f"{prefix}{_(label_key)}", callback_data=f"filter:users:{filter_value}")])

    if current_filter:
        rows.append([InlineKeyboardButton(text=_("actions.filter_clear"), callback_data="filter:users:clear")])

    rows.append(nav_row(NavTarget.SUBS_LIST))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def nodes_filter_keyboard(current_filter: dict | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    current_status = current_filter.get("status") if current_filter else None

    status_filters = [
        ("ONLINE", "filter.nodes.ONLINE"),
        ("OFFLINE", "filter.nodes.OFFLINE"),
        ("ENABLED", "filter.nodes.ENABLED"),
        ("DISABLED", "filter.nodes.DISABLED"),
    ]

    for filter_value, label_key in status_filters:
        prefix = "✓ " if current_status == filter_value else ""
        rows.append([InlineKeyboardButton(text=f"{prefix}{_(label_key)}", callback_data=f"filter:nodes:status:{filter_value}")])

    current_tag = current_filter.get("tag") if current_filter else None
    tag_prefix = "✓ " if current_tag else ""
    rows.append([InlineKeyboardButton(text=f"{tag_prefix}{_('filter.nodes.by_tag')}", callback_data="filter:nodes:tag:select")])

    if current_filter:
        rows.append([InlineKeyboardButton(text=_("actions.filter_clear"), callback_data="filter:nodes:clear")])

    rows.append(nav_row(NavTarget.NODES_LIST))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def nodes_tag_filter_keyboard(tags: list[str], current_tag: str | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    for tag in sorted(set(tags))[:15]:
        prefix = "✓ " if current_tag == tag else ""
        rows.append([InlineKeyboardButton(text=f"{prefix}🏷 {tag}", callback_data=f"filter:nodes:tag:{tag}")])

    rows.append([InlineKeyboardButton(text=_("actions.back"), callback_data="filter:nodes:show")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def hosts_filter_keyboard(current_filter: str | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    filters = [
        ("ENABLED", "filter.hosts.ENABLED"),
        ("DISABLED", "filter.hosts.DISABLED"),
    ]

    for filter_value, label_key in filters:
        prefix = "✓ " if current_filter == filter_value else ""
        rows.append([InlineKeyboardButton(text=f"{prefix}{_(label_key)}", callback_data=f"filter:hosts:{filter_value}")])

    if current_filter:
        rows.append([InlineKeyboardButton(text=_("actions.filter_clear"), callback_data="filter:hosts:clear")])

    rows.append(nav_row(NavTarget.HOSTS_MENU))
    return InlineKeyboardMarkup(inline_keyboard=rows)
