"""Обработчики для управления динамической конфигурацией бота."""
import os
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.i18n import gettext as _

from src.handlers.common import _edit_text_safe, require_permission
from src.keyboards.bot_config_menu import (
    CATEGORY_EMOJI,
    bot_config_categories_keyboard,
    bot_config_category_items_keyboard,
    bot_config_confirm_keyboard,
    bot_config_item_keyboard,
    bot_config_menu_keyboard,
)
from src.utils.auth import BotAdmin
from shared.config_service import ConfigCategory, ConfigItem, config_service
from shared.logger import logger

router = Router(name="bot_config")


class ConfigInputState(StatesGroup):
    """Состояния для ввода значений конфигурации."""
    waiting_value = State()


# Названия категорий (fallback — локаль используется в handler'ах)
CATEGORY_NAMES = {
    "general": "General",
    "notifications": "Notifications",
    "sync": "Synchronization",
    "reports": "Violation Reports",
}


def _cat_name(cat: str) -> str:
    keys = {
        "general": _("bot_config.cat_general"),
        "notifications": _("bot_config.cat_notifications"),
        "sync": _("bot_config.cat_sync"),
        "reports": _("bot_config.cat_reports"),
    }
    return keys.get(cat, cat.title())


def _format_config_value(item: ConfigItem) -> str:
    """Форматирует значение настройки для отображения."""
    value, source = config_service.get_effective_value(item.key)

    if item.is_secret and value:
        display_value = "••••••••"
    elif value is None:
        display_value = _("bot_config.not_set")
    elif isinstance(value, bool):
        display_value = _("actions.yes") if value else _("actions.no")
    else:
        display_value = str(value)

    source_label = {
        "env": _("bot_config.source_env"),
        "db": _("bot_config.source_db"),
        "default": _("bot_config.source_default"),
        "none": _("bot_config.source_none"),
    }.get(source, source)

    return display_value, source_label


def _format_item_details(item: ConfigItem) -> str:
    """Форматирует детальную информацию о настройке."""
    display_value, source_label = _format_config_value(item)

    lines = [
        f"*{item.display_name or item.key}*",
        "",
        f"📝 {item.description or _('bot_config.no_description')}",
        "",
        f"*{_('bot_config.current_value')}:* `{display_value}`",
        f"*{_('bot_config.source_label')}:* {source_label}",
    ]

    if item.env_var_name:
        lines.append(f"*{_('bot_config.env_var')}:* `{item.env_var_name}`")

    if item.default_value:
        lines.append(f"*{_('bot_config.default_value')}:* `{item.default_value}`")

    if item.options:
        lines.append(f"*{_('bot_config.allowed_values')}:* {', '.join(f'`{o}`' for o in item.options)}")

    lines.append(f"*{_('bot_config.type_label')}:* `{item.value_type.value}`")

    # Информация о .env значении (теперь не блокирует редактирование)
    if item.env_var_name:
        env_val = os.getenv(item.env_var_name)
        if env_val:
            lines.append("")
            lines.append(_("bot_config.env_fallback").format(var=item.env_var_name))

    return "\n".join(lines)


# === Callback handlers ===

@router.callback_query(F.data == "menu:bot_config")
async def show_bot_config_menu(callback: CallbackQuery, admin: BotAdmin) -> None:
    """Показывает главное меню конфигурации бота."""
    text = f"*{_('bot_config.title')}*\n\n{_('bot_config.description')}"
    await _edit_text_safe(callback.message, text, reply_markup=bot_config_menu_keyboard(admin=admin), parse_mode="HTML")


@router.callback_query(F.data == "bot_config:menu")
async def show_bot_config_menu_alt(callback: CallbackQuery, admin: BotAdmin) -> None:
    """Альтернативный callback для меню."""
    await show_bot_config_menu(callback, admin=admin)


@router.callback_query(F.data == "bot_config:categories")
async def show_config_categories(callback: CallbackQuery, admin: BotAdmin) -> None:
    """Показывает список категорий настроек."""
    categories = config_service.get_categories()

    if not categories:
        await callback.answer(_("bot_config.no_categories"), show_alert=True)
        return

    text = f"*{_('bot_config.select_category')}*\n\n"
    for cat in categories:
        emoji = CATEGORY_EMOJI.get(cat, "📁")
        name = _cat_name(cat)
        items = config_service.get_by_category(cat)
        text += f"{emoji} *{name}* — {len(items)} настроек\n"

    await _edit_text_safe(callback.message, text, reply_markup=bot_config_categories_keyboard(categories), parse_mode="HTML")


@router.callback_query(F.data.startswith("bot_config:cat:"))
async def show_category_items(callback: CallbackQuery, admin: BotAdmin) -> None:
    """Показывает настройки категории."""
    parts = callback.data.split(":")
    category = parts[2]
    page = 0

    # Проверяем пагинацию
    if len(parts) > 4 and parts[3] == "page":
        try:
            page = int(parts[4])
        except ValueError:
            page = 0

    items = config_service.get_by_category(category)

    if not items:
        await callback.answer(_("bot_config.no_settings"), show_alert=True)
        return

    emoji = CATEGORY_EMOJI.get(category, "📁")
    name = _cat_name(category)

    text = f"*{emoji} {name}*\n\n"
    text += _("bot_config.category_hint")
    text += "\n\n"
    text += _("bot_config.legend_env") + "\n"
    text += _("bot_config.legend_db") + "\n"
    text += _("bot_config.legend_default")

    await _edit_text_safe(
        callback.message,
        text,
        reply_markup=bot_config_category_items_keyboard(category, items, page),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("bot_config:item:"))
async def show_config_item(callback: CallbackQuery, admin: BotAdmin) -> None:
    """Показывает детали настройки."""
    key = callback.data.split(":")[2]
    item = config_service.get_raw(key)

    if not item:
        await callback.answer(_("bot_config.not_found"), show_alert=True)
        return

    text = _format_item_details(item)
    await _edit_text_safe(callback.message, text, reply_markup=bot_config_item_keyboard(item), parse_mode="HTML")


@router.callback_query(F.data.startswith("bot_config:set:"))
async def set_config_value(callback: CallbackQuery, admin: BotAdmin) -> None:
    """Устанавливает значение настройки."""
    if not await require_permission(callback, admin, "settings", "edit"):
        return
    parts = callback.data.split(":")
    key = parts[2]
    value = ":".join(parts[3:])  # На случай если значение содержит ":"

    item = config_service.get_raw(key)
    if not item:
        await callback.answer(_("bot_config.not_found"), show_alert=True)
        return

    # Устанавливаем значение (БД имеет приоритет над .env)
    success = await config_service.set(key, value)

    if success:
        await callback.answer(_("bot_config.saved"), show_alert=False)
        # Обновляем экран с деталями
        await show_config_item(callback, admin=admin)
    else:
        await callback.answer(_("bot_config.save_error"), show_alert=True)


@router.callback_query(F.data.startswith("bot_config:input:"))
async def request_config_input(callback: CallbackQuery, state: FSMContext, admin: BotAdmin) -> None:
    """Запрашивает ввод значения настройки."""
    key = callback.data.split(":")[2]
    item = config_service.get_raw(key)

    if not item:
        await callback.answer(_("bot_config.not_found"), show_alert=True)
        return

    # Сохраняем контекст и просим ввод (БД имеет приоритет над .env)
    await state.set_state(ConfigInputState.waiting_value)
    await state.update_data(config_key=key, message_id=callback.message.message_id)

    type_hints = {
        "string": _("bot_config.type_hint_string"),
        "int": _("bot_config.type_hint_int"),
        "float": _("bot_config.type_hint_float"),
        "bool": "true/false",
        "json": _("bot_config.type_hint_json"),
    }

    hint = type_hints.get(item.value_type.value, _("bot_config.type_hint_fallback"))
    text = f"*{_('bot_config.enter_value_prompt')}*\n\n"
    text += f"*{_('bot_config.setting_label')}:* {item.display_name or item.key}\n"
    text += f"*{_('bot_config.expected_type')}:* _{hint}_\n\n"
    text += _("bot_config.send_value_or_cancel")

    await callback.message.edit_text(text, parse_mode="HTML")


@router.message(ConfigInputState.waiting_value)
async def process_config_input(message: Message, state: FSMContext) -> None:
    """Обрабатывает введённое значение настройки."""
    # Отмена
    if message.text and message.text.lower() in ("/cancel", _("common.cancel").lower()):
        await state.clear()
        await message.answer(_("bot_config.input_cancelled"))
        return

    data = await state.get_data()
    key = data.get("config_key")

    if not key:
        await state.clear()
        await message.answer(_("bot_config.input_error"))
        return

    item = config_service.get_raw(key)
    if not item:
        await state.clear()
        await message.answer(_("bot_config.not_found"))
        return

    value = message.text.strip() if message.text else ""

    # Валидация по допустимым опциям (если заданы)
    if item.options:
        if value not in item.options:
            await message.answer(
                _("bot_config.validation_invalid_value").format(
                    value=value,
                    allowed=", ".join(f"`{o}`" for o in item.options),
                ),
                parse_mode="HTML"
            )
            return

    # Валидация типа
    import json as json_module
    try:
        if item.value_type.value == "int":
            parsed_int = int(value)
            # Проверка на отрицательные значения для некоторых настроек
            if parsed_int < 0 and item.key in (
                "sync_interval_seconds",
            ):
                raise ValueError(_("bot_config.validation_positive_required"))
        elif item.value_type.value == "float":
            parsed_float = float(value)
            if parsed_float < 0 and "multiplier" not in item.key:
                raise ValueError(_("bot_config.validation_positive_required"))
        elif item.value_type.value == "bool":
            if value.lower() not in ("true", "false", "1", "0", "yes", "no", "on", "off"):
                raise ValueError(_("bot_config.validation_bool_hint"))
        elif item.value_type.value == "json":
            json_module.loads(value)
    except ValueError as e:
        type_hints = {
            "int": _("bot_config.validation_hint_int"),
            "float": _("bot_config.validation_hint_float"),
            "bool": "true/false, yes/no, on/off, 1/0",
            "json": _("bot_config.validation_hint_json"),
        }
        hint = type_hints.get(item.value_type.value, "")
        await message.answer(
            _("bot_config.validation_error").format(value=value, hint=hint),
            parse_mode="HTML"
        )
        return
    except json_module.JSONDecodeError:
        await message.answer(
            _("bot_config.invalid_json"),
            parse_mode="HTML"
        )
        return

    # Сохраняем значение
    success = await config_service.set(key, value)
    await state.clear()

    if success:
        await message.answer(
            _("bot_config.saved_with_value").format(
                name=item.display_name or item.key,
                value=value,
            ),
            parse_mode="HTML"
        )
    else:
        await message.answer(_("bot_config.save_error"))


@router.callback_query(F.data.startswith("bot_config:reset:"))
async def confirm_reset_config(callback: CallbackQuery, admin: BotAdmin) -> None:
    """Подтверждение сброса настройки."""
    if not await require_permission(callback, admin, "settings", "edit"):
        return
    key = callback.data.split(":")[2]
    item = config_service.get_raw(key)

    if not item:
        await callback.answer(_("bot_config.not_found"), show_alert=True)
        return

    text = f"*{_('bot_config.confirm_reset')}*\n\n"
    text += f"*{_('bot_config.setting_label')}:* {item.display_name or item.key}\n"
    text += _("bot_config.reset_to").format(default=item.default_value or _("bot_config.empty_value"))

    await _edit_text_safe(callback.message, text, reply_markup=bot_config_confirm_keyboard(key, "reset"), parse_mode="HTML")


@router.callback_query(F.data.startswith("bot_config:confirm:reset:"))
async def reset_config_value(callback: CallbackQuery, admin: BotAdmin) -> None:
    """Сбрасывает настройку к значению по умолчанию."""
    if not await require_permission(callback, admin, "settings", "edit"):
        return
    key = callback.data.split(":")[3]

    success = await config_service.reset_to_default(key)

    if success:
        await callback.answer(_("bot_config.reset_done"), show_alert=False)
        # Создаём фейковый callback для показа детлей
        callback.data = f"bot_config:item:{key}"
        await show_config_item(callback, admin=admin)
    else:
        await callback.answer(_("bot_config.reset_error"), show_alert=True)


@router.callback_query(F.data == "bot_config:reload")
async def reload_config(callback: CallbackQuery, admin: BotAdmin) -> None:
    """Перезагружает конфигурацию из БД."""
    await config_service.reload()
    await callback.answer(_("bot_config.reloaded"), show_alert=True)
    await show_bot_config_menu(callback, admin=admin)


@router.callback_query(F.data == "bot_config:all")
async def show_all_settings(callback: CallbackQuery, admin: BotAdmin) -> None:
    """Показывает все настройки (краткий обзор)."""
    all_items = config_service.get_all()

    if not all_items:
        await callback.answer(_("bot_config.no_settings"), show_alert=True)
        return

    lines = [f"*{_('bot_config.all_settings_title')}*", ""]

    # Собираем все источники для динамической легенды
    sources_used: set[str] = set()
    settings_data: list[tuple] = []

    current_category = None
    for item in sorted(all_items.values(), key=lambda x: (x.category.value, x.sort_order)):
        display_value, source = _format_config_value(item)
        source_key = source.split()[0].lower() if source else ""
        sources_used.add(source_key)
        settings_data.append((item, display_value, source_key))

    # Добавляем динамическую легенду (только используемые источники)
    legend_parts = []
    if "env" in sources_used:
        legend_parts.append(_("bot_config.legend_env"))
    if "db" in sources_used:
        legend_parts.append(_("bot_config.legend_modified"))
    if "default" in sources_used:
        legend_parts.append(_("bot_config.legend_default_lower"))

    if legend_parts:
        lines.append(f"_{' • '.join(legend_parts)}_")
        lines.append("")

    # Выводим настройки
    for item, display_value, source_key in settings_data:
        if item.category.value != current_category:
            current_category = item.category.value
            emoji = CATEGORY_EMOJI.get(current_category, "📁")
            name = _cat_name(current_category)
            lines.append(f"\n*{emoji} {name}*")

        source_icon = {"env": "🔒", "db": "💾", "default": "📋"}.get(source_key, "⚪")
        lines.append(f"  {source_icon} {item.display_name or item.key}: `{display_value}`")

    # Ограничиваем длину сообщения
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + _("bot_config.truncated")

    await _edit_text_safe(callback.message, text, reply_markup=bot_config_menu_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "noop")
async def noop_handler(callback: CallbackQuery, admin: BotAdmin) -> None:
    """Пустой обработчик для информационных кнопок."""
    await callback.answer()
