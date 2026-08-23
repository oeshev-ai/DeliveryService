"""Клавиатуры Telegram для согласия, меню, статуса и WebApp."""

from __future__ import annotations

from urllib.parse import urlparse

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from delivery_bot.logging_setup import get_logger

logger = get_logger(__name__)


def is_telegram_webapp_url(url: str | None) -> bool:
    """Telegram принимает WebApp URL только по HTTPS."""
    if not url:
        return False
    parsed = urlparse(url.strip())
    return parsed.scheme == "https" and bool(parsed.netloc)


def consent_keyboard() -> InlineKeyboardMarkup:
    """Кнопки принятия / отклонения согласия на ПДн."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Принимаю",
                    callback_data="consent:accept",
                ),
                InlineKeyboardButton(
                    text="❌ Не принимаю",
                    callback_data="consent:decline",
                ),
            ]
        ]
    )


def main_menu_keyboard(*, active_order_id: str | None = None) -> InlineKeyboardMarkup:
    """Главное меню; при активном заказе — персональная кнопка статуса."""
    rows: list[list[InlineKeyboardButton]] = []

    if active_order_id:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"📦 Статус {active_order_id}",
                    callback_data="menu:status",
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔎 Другой заказ",
                    callback_data="menu:status_new",
                )
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(text="📦 Статус заказа", callback_data="menu:status"),
            ]
        )

    rows.extend(
        [
            [
                InlineKeyboardButton(text="🚴 Курьер", callback_data="menu:courier"),
                InlineKeyboardButton(text="✏️ Изменить заказ", callback_data="menu:change"),
            ],
            [
                InlineKeyboardButton(text="🚫 Отмена", callback_data="menu:cancel"),
                InlineKeyboardButton(text="❓ FAQ", callback_data="menu:faq"),
            ],
            [
                InlineKeyboardButton(text="⚠️ Претензия", callback_data="menu:claim"),
                InlineKeyboardButton(text="⭐ Отзыв", callback_data="menu:review"),
            ],
            [
                InlineKeyboardButton(text="🔁 Повторить заказ", callback_data="menu:reorder"),
                InlineKeyboardButton(text="👤 Оператор", callback_data="menu:operator"),
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def order_status_keyboard(
    order_id: str,
    *,
    webapp_url: str | None = None,
) -> InlineKeyboardMarkup:
    """Клавиатура после показа статуса: WebApp (только HTTPS) + меню."""
    rows: list[list[InlineKeyboardButton]] = []
    if is_telegram_webapp_url(webapp_url):
        url = _webapp_order_url(webapp_url or "", order_id)
        rows.append(
            [
                InlineKeyboardButton(
                    text="📱 Открыть виджет статуса",
                    web_app=WebAppInfo(url=url),
                )
            ]
        )
    elif webapp_url:
        logger.warning(
            "webapp_button_skipped_non_https",
            webapp_url=webapp_url,
            hint="Telegram требует HTTPS для Mini App",
        )
    rows.append(
        [
            InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main"),
            InlineKeyboardButton(text="🔎 Другой заказ", callback_data="menu:status_new"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def order_list_keyboard(
    order_ids: list[str],
    *,
    active_order_id: str | None = None,
    webapp_url: str | None = None,
) -> InlineKeyboardMarkup:
    """Кнопки выбора заказа из списка + WebApp + меню."""
    rows: list[list[InlineKeyboardButton]] = []
    if is_telegram_webapp_url(webapp_url) and active_order_id:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📱 Виджет статуса",
                    web_app=WebAppInfo(
                        url=_webapp_order_url(webapp_url or "", active_order_id)
                    ),
                )
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text=("✅ " if oid == active_order_id else "") + oid,
                    callback_data=f"order:select:{oid}",
                )
            ]
            for oid in order_ids[:8]
        ]
    )
    rows.append([InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def continue_session_keyboard() -> InlineKeyboardMarkup:
    """Кнопка продления диалога после истечения сессии."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="▶️ Продолжить диалог",
                    callback_data="session:continue",
                )
            ]
        ]
    )


def _webapp_order_url(webapp_url: str, order_id: str) -> str:
    """Собирает URL Mini App с order_id."""
    base = webapp_url.rstrip("/")
    return f"{base}/?order_id={order_id}"
