"""Пакет платежей."""

from delivery_bot.integrations.payments.mock import MockPaymentGateway, PaymentResult

__all__ = ["MockPaymentGateway", "PaymentResult"]
