from aiogram.types import InlineKeyboardMarkup

from src.keyboards.navigation import NavTarget, nav_row


def config_actions_keyboard(profile_uuid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[nav_row(NavTarget.CONFIGS_MENU)])
