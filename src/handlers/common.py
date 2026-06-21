"""Общие утилиты для всех обработчиков."""
import asyncio
from typing import Awaitable, Callable, Optional

from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.i18n import gettext as _

from src.handlers.state import ADMIN_COMMAND_DELETE_DELAY, BACKGROUND_TASKS, LAST_BOT_MESSAGES, LAST_BOT_MESSAGES_LOCK
from shared.internal_api import ApiClientError, NotFoundError, UnauthorizedError
from src.utils.auth import BotAdmin, resolve_admin
from shared.logger import logger


async def _cleanup_message(message: Message, delay: float = 0.0) -> None:
    """Удаляет сообщение с задержкой."""
    if not isinstance(message, Message):
        return
    try:
        if delay > 0:
            await asyncio.sleep(delay)
        await message.delete()
    except Exception as exc:
        logger.warning(
            "🧹 Failed to delete message chat_id=%s message_id=%s err=%s",
            message.chat.id,
            getattr(message, "message_id", None),
            exc,
        )


def track_task(coro) -> asyncio.Task:
    """Create a tracked asyncio task that auto-removes from BACKGROUND_TASKS on completion."""
    task = asyncio.create_task(coro)
    BACKGROUND_TASKS.add(task)
    task.add_done_callback(BACKGROUND_TASKS.discard)
    return task


def _schedule_message_cleanup(message: Message, delay: float = 0.5) -> None:
    """Планирует удаление сообщения пользователя после обработки."""
    if isinstance(message, Message):
        track_task(_cleanup_message(message, delay=delay))


async def _send_clean_message(
    target: Message | CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = None,
) -> Message:
    """Отправляет или редактирует сообщение, заменяя предыдущее в чате."""
    msg = target.message if isinstance(target, CallbackQuery) else target
    bot = msg.bot
    chat_id = msg.chat.id

    async with LAST_BOT_MESSAGES_LOCK:
        prev_id = LAST_BOT_MESSAGES.get(chat_id)
        if prev_id:
            try:
                edited = await bot.edit_message_text(
                    chat_id=chat_id, message_id=prev_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode
                )
                return edited
            except Exception:
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=prev_id)
                except Exception:
                    pass

        sent = await msg.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
        LAST_BOT_MESSAGES[chat_id] = sent.message_id
        return sent


async def _not_admin(message: Message | CallbackQuery) -> bool:
    """Проверяет, является ли пользователь администратором с доступом к боту. Удаляет команды автоматически."""
    from src.handlers.state import PENDING_INPUT
    
    user_id = message.from_user.id if hasattr(message, "from_user") else None
    if user_id is None:
        return True

    admin = await resolve_admin(user_id)
    if admin is None:
        text = _("errors.unauthorized")
        if isinstance(message, CallbackQuery):
            await message.answer(text, show_alert=True)
        else:
            await _send_clean_message(message, text)
        return True

    if not admin.is_superadmin and not admin.has_bot_access:
        text = _("errors.no_bot_access_title") + "\n\n" + _("errors.no_bot_access")
        if isinstance(message, CallbackQuery):
            await message.answer(text, show_alert=True)
        else:
            await _send_clean_message(message, text)
        return True

    if isinstance(message, Message):
        is_command = bool(getattr(message, "text", "") and message.text.startswith("/"))
        is_pending_input = user_id in PENDING_INPUT
        if is_command:
            delay = ADMIN_COMMAND_DELETE_DELAY
            track_task(_cleanup_message(message, delay=delay))
        elif not is_pending_input:
            pass
    return False


async def require_permission(
    target: Message | CallbackQuery,
    admin: BotAdmin,
    resource: str,
    action: str,
) -> bool:
    """Check admin has permission. Returns True if allowed, False if denied (sends error)."""
    if await admin.has_permission(resource, action):
        return True
    text = _("errors.permission_denied")
    if isinstance(target, CallbackQuery):
        await target.answer(text, show_alert=True)
    else:
        await _send_clean_message(target, text)
    return False


def _get_target_user_id(target: Message | CallbackQuery) -> int | None:
    """Извлекает user_id из Message или CallbackQuery."""
    if isinstance(target, CallbackQuery):
        return target.from_user.id
    return target.from_user.id if getattr(target, "from_user", None) else None


def _clear_user_state(user_id: int | None, keep_search: bool = False, keep_subs: bool = False) -> None:
    """Очищает состояние пользователя."""
    from src.handlers.state import (
        PENDING_INPUT,
        SUBS_PAGE_BY_USER,
        USER_DETAIL_BACK_TARGET,
        USER_SEARCH_CONTEXT,
    )

    if user_id is None:
        return
    # НЕ удаляем PENDING_INPUT, если это поиск - он будет установлен в _start_user_search_flow
    # PENDING_INPUT должен сохраняться для ожидаемого ввода
    if not keep_search:
        PENDING_INPUT.pop(user_id, None)
        USER_SEARCH_CONTEXT.pop(user_id, None)
        USER_DETAIL_BACK_TARGET.pop(user_id, None)
        if not keep_subs:
            SUBS_PAGE_BY_USER.pop(user_id, None)


async def _edit_text_safe(
    message: Message, text: str, reply_markup: InlineKeyboardMarkup | None = None, parse_mode: str | None = None
) -> None:
    """Безопасно редактирует текст сообщения, обрабатывая ошибки."""
    from aiogram.exceptions import TelegramBadRequest

    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc):
            # Сообщение не изменилось - это нормально, просто игнорируем
            return
        # Другие ошибки - пробуем отправить новое сообщение
        try:
            await message.delete()
        except Exception:
            pass
        await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception:
        # Любая другая ошибка - пробуем отправить новое сообщение
        try:
            await message.delete()
        except Exception:
            pass
        await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)


async def _fetch_data(
    fetch_fn: Callable[[], Awaitable[dict]],
    logger_msg: str = "",
) -> dict | str:
    """Fetch data from API, returning response dict or error string on failure."""
    try:
        return await fetch_fn()
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        if logger_msg:
            logger.exception(logger_msg)
        return _("errors.generic")


def _get_error_message(exc: Exception, include_code: bool = True, include_hint: bool = True) -> str:
    """Возвращает понятное сообщение об ошибке на основе типа исключения.
    
    Args:
        exc: Исключение для обработки
        include_code: Включать ли код ошибки в сообщение
        include_hint: Включать ли подсказку по исправлению
    
    Returns:
        Форматированное сообщение об ошибке
    """
    from shared.internal_api import (
        ApiClientError,
        NetworkError,
        NotFoundError,
        RateLimitError,
        ServerError,
        TimeoutError,
        UnauthorizedError,
        ValidationError,
    )
    
    def _safe_gettext(key: str, fallback: str) -> str:
        """Безопасный вызов gettext с fallback."""
        try:
            return _(key)
        except LookupError:
            return fallback
    
    # Определяем базовое сообщение, код и подсказку
    message = ""
    error_code = ""
    hint = ""
    
    if isinstance(exc, UnauthorizedError):
        message = _safe_gettext("errors.unauthorized", "⛔️ Нет доступа. Проверь API токен в настройках.")
        error_code = exc.code
        hint = _safe_gettext("errors.hint_unauthorized", "Проверь API токен в настройках бота")
    elif isinstance(exc, NotFoundError):
        message = _safe_gettext("errors.not_found", "❌ Объект не найден. Возможно, он был удален.")
        error_code = exc.code
        hint = _safe_gettext("errors.hint_not_found", "Убедись, что объект существует и не был удален")
    elif isinstance(exc, TimeoutError):
        message = _safe_gettext("errors.timeout_error", "⏱ Превышено время ожидания ответа от сервера.")
        error_code = exc.code
        hint = _safe_gettext("errors.hint_timeout", "Сервер перегружен или медленно отвечает. Попробуй позже")
    elif isinstance(exc, NetworkError):
        message = _safe_gettext("errors.network_error", "🌐 Ошибка сети. Не удалось подключиться к серверу.")
        error_code = exc.code
        hint = _safe_gettext("errors.hint_network", "Проверь подключение к интернету и доступность API сервера")
    elif isinstance(exc, RateLimitError):
        message = _safe_gettext("errors.rate_limit", "🚦 Превышен лимит запросов.")
        error_code = exc.code
        hint = _safe_gettext("errors.hint_rate_limit", "Подожди немного перед повторной попыткой")
    elif isinstance(exc, ServerError):
        message = _safe_gettext("errors.server_error", "🔴 Ошибка сервера. Сервис временно недоступен.")
        error_code = exc.code
        hint = _safe_gettext("errors.hint_server", "Сервер временно недоступен. Попробуй через несколько минут")
    elif isinstance(exc, ValidationError):
        message = _safe_gettext("errors.validation_error", "⚠️ Ошибка валидации данных. Проверь введенные значения.")
        error_code = exc.code
        # Для ошибок валидации добавляем информацию о поле, если есть
        if exc.field:
            try:
                hint = _("errors.hint_validation_field").format(field=exc.field)
            except LookupError:
                hint = f"Проверь формат введенных данных (поле: {exc.field})"
        else:
            hint = _safe_gettext("errors.hint_validation", "Проверь формат введенных данных")
    elif isinstance(exc, ApiClientError):
        # Общая ошибка API
        message = _safe_gettext("errors.generic", "⚠️ Что-то пошло не так. Повтори чуть позже.")
        error_code = getattr(exc, "code", "ERR_API_000")
        hint = _safe_gettext("errors.hint_generic", "Попробуй повторить операцию позже")
    else:
        # Для других типов ошибок возвращаем общее сообщение
        message = _safe_gettext("errors.generic", "⚠️ Что-то пошло не так. Повтори чуть позже.")
        error_code = "ERR_UNK_001"
        hint = _safe_gettext("errors.hint_generic", "Попробуй повторить операцию позже")
    
    # Формируем финальное сообщение
    parts = [message]
    
    if include_hint and hint:
        parts.append(f"\n💡 {hint}")
    
    if include_code and error_code:
        parts.append(f"\n🔢 Код: `{error_code}`")
    
    return "".join(parts)

