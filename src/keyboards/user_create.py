from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row


def user_create_description_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=_("user.skip"), callback_data="user_create:skip:description")]]
    )


def user_create_expire_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=_("user.expire_7d"), callback_data="user_create:expire:7"),
                InlineKeyboardButton(text=_("user.expire_30d"), callback_data="user_create:expire:30"),
            ],
            [
                InlineKeyboardButton(text=_("user.expire_90d"), callback_data="user_create:expire:90"),
                InlineKeyboardButton(text=_("user.expire_365d"), callback_data="user_create:expire:365"),
            ],
            [
                InlineKeyboardButton(text=_("user.expire_2099"), callback_data="user_create:expire:2099"),
            ],
        ]
    )


def user_create_traffic_keyboard(policy: str = "allowed") -> InlineKeyboardMarkup:
    """Traffic limit keyboard.
    
    Args:
        policy: "allowed" | "disabled" | "enforced"
        - "allowed": show all options including unlimited
        - "disabled": show limited options, NO unlimited
        - "enforced": show only unlimited (auto-selected)
    """
    if policy == "enforced":
        # Auto-unlimited, just show info button
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=_("user.traffic_unlimited"), callback_data="user_create:traffic:unlimited")],
            ]
        )
    
    rows = [
        [
            InlineKeyboardButton(text=_("user.traffic_5"), callback_data="user_create:traffic:5"),
            InlineKeyboardButton(text=_("user.traffic_10"), callback_data="user_create:traffic:10"),
        ],
        [
            InlineKeyboardButton(text=_("user.traffic_20"), callback_data="user_create:traffic:20"),
            InlineKeyboardButton(text=_("user.traffic_50"), callback_data="user_create:traffic:50"),
        ],
        [
            InlineKeyboardButton(text=_("user.traffic_100"), callback_data="user_create:traffic:100"),
            InlineKeyboardButton(text=_("user.traffic_500"), callback_data="user_create:traffic:500"),
        ],
        [
            InlineKeyboardButton(text=_("user.traffic_custom"), callback_data="user_create:traffic:custom"),
        ],
    ]
    
    if policy == "allowed":
        rows.append([InlineKeyboardButton(text=_("user.traffic_unlimited"), callback_data="user_create:traffic:unlimited")])
    
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_create_traffic_strategy_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=_("user.strategy_no_reset"), callback_data="user_create:traffic_strategy:NO_RESET"),
                InlineKeyboardButton(text=_("user.strategy_monthly"), callback_data="user_create:traffic_strategy:MONTHLY"),
            ],
            [
                InlineKeyboardButton(text=_("user.strategy_weekly"), callback_data="user_create:traffic_strategy:WEEKLY"),
                InlineKeyboardButton(text=_("user.strategy_daily"), callback_data="user_create:traffic_strategy:DAILY"),
            ],
        ]
    )


def user_create_hwid_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=_("user.hwid_1"), callback_data="user_create:hwid:1"),
                InlineKeyboardButton(text=_("user.hwid_2"), callback_data="user_create:hwid:2"),
            ],
            [
                InlineKeyboardButton(text=_("user.hwid_3"), callback_data="user_create:hwid:3"),
                InlineKeyboardButton(text=_("user.hwid_4"), callback_data="user_create:hwid:4"),
            ],
            [
                InlineKeyboardButton(text=_("user.hwid_5"), callback_data="user_create:hwid:5"),
                InlineKeyboardButton(text=_("user.hwid_10"), callback_data="user_create:hwid:10"),
            ],
            [
                InlineKeyboardButton(text=_("user.hwid_custom"), callback_data="user_create:hwid:custom"),
            ],
            [
                InlineKeyboardButton(text=_("user.hwid_unlimited"), callback_data="user_create:hwid:0"),
            ],
        ]
    )


def user_create_telegram_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=_("user.skip"), callback_data="user_create:skip:telegram")]]
    )


def user_create_email_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=_("user.skip"), callback_data="user_create:skip:email")]]
    )


def user_create_tag_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=_("user.skip"), callback_data="user_create:skip:tag")]]
    )


def user_create_uuid_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("user.uuid_auto"), callback_data="user_create:uuid:auto")],
            [InlineKeyboardButton(text=_("user.skip"), callback_data="user_create:skip:uuid")],
        ]
    )


def user_create_squad_keyboard(squads: list[dict]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=s.get("name", "n/a"), callback_data=f"user_create:squad:{s.get('uuid')}")] for s in squads]
    rows.append([InlineKeyboardButton(text=_("user.skip"), callback_data="user_create:skip:squad")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_create_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=_("user.confirm_create"), callback_data="user_create:confirm"),
                InlineKeyboardButton(text=_("user.cancel_create"), callback_data="user_create:cancel"),
            ],
            nav_row(NavTarget.USERS_MENU),
        ]
    )
