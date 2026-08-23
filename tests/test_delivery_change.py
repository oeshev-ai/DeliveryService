"""Тесты правил доставки и смены адреса."""

from decimal import Decimal

from delivery_bot.services.delivery_rules import (
    get_min_order_amount,
    list_slots,
    quote_address_change,
)
from delivery_bot.services.order_policy import can_change_address, can_change_time


def test_min_order_and_slots_from_api() -> None:
    assert get_min_order_amount() == Decimal("500.00")
    slots = list_slots()
    assert len(slots) >= 3
    assert all(s.id and s.label for s in slots)


def test_address_in_zone_no_surcharge() -> None:
    quote = quote_address_change("Москва, ул. Арбат, 15")
    assert quote.ok is True
    assert quote.in_zone is True
    assert quote.surcharge == Decimal("0.00")


def test_address_surcharge_suburb() -> None:
    quote = quote_address_change("Химки, ул. Ленина, 1")
    assert quote.ok is True
    assert quote.surcharge > 0


def test_address_out_of_zone() -> None:
    quote = quote_address_change("Казань, ул. Баумана, 1")
    assert quote.ok is False
    assert quote.in_zone is False


def test_address_change_policy_before_assembling() -> None:
    assert can_change_address("paid") is True
    assert can_change_address("assembling") is False
    assert can_change_time("assembling") is True
    assert can_change_time("handed_to_courier") is False
