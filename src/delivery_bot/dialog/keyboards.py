"""Клавиатуры Telegram для согласия, меню и продления сессии."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


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


def order_list_keyboard(
    order_ids: list[str],
    *,
    active_order_id: str | None = None,
) -> InlineKeyboardMarkup:
    """Кнопки выбора заказа из списка + меню."""
    rows = [
        [
            InlineKeyboardButton(
                text=("✅ " if oid == active_order_id else "") + oid,
                callback_data=f"order:select:{oid}",
            )
        ]
        for oid in order_ids[:8]
    ]
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
