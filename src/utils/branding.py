"""Бренд-нейминг бота.

Отображаемое имя проекта берётся из настройки ``panel_name`` (таблица
bot_config, редактируется суперадмином в настройках веб-панели). Если имя не
задано — используется дефолт ``Remnawave Admin``. Так бот и веб-панель
показывают единое название бренда.
"""

DEFAULT_BRAND = "Remnawave Admin"


def brand_name() -> str:
    """Отображаемое имя проекта: panel_name из config_service или дефолт."""
    try:
        from shared.config_service import config_service

        if config_service._initialized:
            name = (config_service.get("panel_name", "") or "").strip()
            if name:
                return name
    except Exception:
        pass
    return DEFAULT_BRAND


def bot_menu_title() -> str:
    """Заголовок главного меню бота (эмодзи + имя бренда)."""
    return f"🤖 {brand_name()}"
