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


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню с персональными точками входа в сценарии."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📦 Статус заказа", callback_data="menu:status"),
                InlineKeyboardButton(text="🚴 Курьер", callback_data="menu:courier"),
            ],
            [
                InlineKeyboardButton(text="✏️ Изменить заказ", callback_data="menu:change"),
                InlineKeyboardButton(text="🚫 Отмена", callback_data="menu:cancel"),
            ],
            [
                InlineKeyboardButton(text="❓ FAQ", callback_data="menu:faq"),
                InlineKeyboardButton(text="⚠️ Претензия", callback_data="menu:claim"),
            ],
            [
                InlineKeyboardButton(text="⭐ Отзыв", callback_data="menu:review"),
                InlineKeyboardButton(text="🔁 Повторить заказ", callback_data="menu:reorder"),
            ],
            [
                InlineKeyboardButton(text="👤 Оператор", callback_data="menu:operator"),
            ],
        ]
    )


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
