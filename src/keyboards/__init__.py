from aiogram.types import InlineKeyboardButton

from src.utils.auth import BotAdmin


def perm_btn(admin: BotAdmin | None, resource: str, action: str, text: str, callback_data: str) -> InlineKeyboardButton | None:
    if admin is None or admin.has_perm_sync(resource, action):
        return InlineKeyboardButton(text=text, callback_data=callback_data)
    return None
