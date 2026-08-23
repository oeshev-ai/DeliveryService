"""Пакет интеграции с OMS."""

from delivery_bot.integrations.oms.client import OmsClient, OmsError
from delivery_bot.integrations.oms.schemas import OrderDTO, OrderPublicDTO

__all__ = ["OmsClient", "OmsError", "OrderDTO", "OrderPublicDTO"]
