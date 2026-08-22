"""Состояния диалога (FSM) для Dialog Manager."""

from __future__ import annotations

from enum import StrEnum


class DialogState(StrEnum):
    """Состояния клиентского диалога.

    Итерация 1: каркас FSM + согласие + главное меню.
    Остальные состояния — задел под сценарии итераций 2+.
    """

    IDLE = "idle"
    AWAITING_CONSENT = "awaiting_consent"
    MAIN_MENU = "main_menu"
    SESSION_EXPIRED = "session_expired"

    # Задел под следующие итерации
    AWAITING_ORDER_ID = "awaiting_order_id"
    AWAITING_PHONE_LAST4 = "awaiting_phone_last4"
    ORDER_STATUS = "order_status"
    CHANGE_ORDER = "change_order"
    CANCEL_ORDER = "cancel_order"
    FAQ = "faq"
    CLAIM = "claim"
    REVIEW = "review"
    REORDER = "reorder"
    ESCALATED = "escalated"
