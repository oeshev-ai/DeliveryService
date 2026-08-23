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
    CHANGE_MENU = "change_menu"
    CHANGE_AWAITING_ADDRESS = "change_awaiting_address"
    CHANGE_CONFIRM_PAY = "change_confirm_pay"
    CHANGE_AWAITING_SLOT = "change_awaiting_slot"
    CANCEL_ORDER = "cancel_order"
    CANCEL_MENU = "cancel_menu"
    CANCEL_AWAITING_REASON = "cancel_awaiting_reason"
    CANCEL_AWAITING_COMMENT = "cancel_awaiting_comment"
    CANCEL_CONFIRM = "cancel_confirm"
    CANCEL_SELECT_ITEMS = "cancel_select_items"
    FAQ = "faq"
    CLAIM = "claim"
    REVIEW = "review"
    REORDER = "reorder"
    ESCALATED = "escalated"
