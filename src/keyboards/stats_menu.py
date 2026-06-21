from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row


def stats_menu_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=_("stats.panel_stats"), callback_data="stats:panel")],
        [InlineKeyboardButton(text=_("stats.server_stats"), callback_data="stats:server")],
        [InlineKeyboardButton(text=_("stats.traffic_stats"), callback_data="stats:traffic")],
        [InlineKeyboardButton(text=_("stats.extended_stats"), callback_data="stats:extended")],
        [InlineKeyboardButton(text=_("actions.refresh"), callback_data="stats:refresh")],
        nav_row(NavTarget.SYSTEM_MENU),
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def stats_period_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text=_("stats.period_today"), callback_data="stats:traffic_period:today"),
            InlineKeyboardButton(text=_("stats.period_week"), callback_data="stats:traffic_period:week"),
        ],
        [
            InlineKeyboardButton(text=_("stats.period_month"), callback_data="stats:traffic_period:month"),
            InlineKeyboardButton(text=_("stats.period_3months"), callback_data="stats:traffic_period:3months"),
        ],
        [
            InlineKeyboardButton(text=_("stats.period_year"), callback_data="stats:traffic_period:year"),
        ],
        nav_row(NavTarget.STATS_MENU),
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
