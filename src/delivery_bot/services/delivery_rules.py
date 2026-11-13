"""Правила доставки из «API»: зоны, слоты, мин. сумма, доплата."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class DeliverySlot:
    """Слот доставки."""

    id: str
    label: str


@dataclass(frozen=True, slots=True)
class AddressQuote:
    """Результат проверки нового адреса."""

    ok: bool
    in_zone: bool
    surcharge: Decimal
    message: str
    normalized_address: str


# Mock «справочник из API»
MIN_ORDER_AMOUNT = Decimal("500.00")

DELIVERY_SLOTS: tuple[DeliverySlot, ...] = (
    DeliverySlot("slot_today_16_18", "сегодня 16:00–18:00"),
    DeliverySlot("slot_today_18_20", "сегодня 18:00–20:00"),
    DeliverySlot("slot_today_20_22", "сегодня 20:00–22:00"),
    DeliverySlot("slot_tomorrow_12_14", "завтра 12:00–14:00"),
)

# Адреса вне зоны (подстроки, lower)
_OUT_OF_ZONE_MARKERS = (
    "казань",
    "санкт-петербург",
    "спб",
    "новосибирск",
    "вне зоны",
    "другой город",
)

# Адреса с доплатой
_SURCHARGE_MARKERS = (
    "зеленоград",
    "новая москва",
    "химки",
    "мытищи",
    "люберцы",
    "одинцово",
)

_DEFAULT_SURCHARGE = Decimal("250.00")


def list_slots() -> list[DeliverySlot]:
    """Слоты доставки из API (мок)."""
    return list(DELIVERY_SLOTS)


def get_min_order_amount() -> Decimal:
    return MIN_ORDER_AMOUNT


def quote_address_change(address: str) -> AddressQuote:
    """Проверяет зону и считает доплату за новый адрес."""
    normalized = " ".join(address.strip().split())
    if len(normalized) < 5:
        return AddressQuote(
            ok=False,
            in_zone=False,
            surcharge=Decimal("0"),
            message="Адрес слишком короткий. Укажите улицу и дом.",
            normalized_address=normalized,
        )

    lower = normalized.lower()
    if any(m in lower for m in _OUT_OF_ZONE_MARKERS):
        return AddressQuote(
            ok=False,
            in_zone=False,
            surcharge=Decimal("0"),
            message=(
                "Этот адрес вне зоны доставки — изменить нельзя.\n"
                "Нажмите «Связаться с оператором», если нужна помощь."
            ),
            normalized_address=normalized,
        )

    # Базово принимаем Москву и область с маркерами доплаты
    if "москв" not in lower and not any(m in lower for m in _SURCHARGE_MARKERS):
        # неизвестный регион — считаем вне зоны
        return AddressQuote(
            ok=False,
            in_zone=False,
            surcharge=Decimal("0"),
            message=(
                "Не удалось подтвердить зону доставки для этого адреса. "
                "Укажите адрес в Москве или ближайшем Подмосковье, "
                "либо напишите «оператор»."
            ),
            normalized_address=normalized,
        )

    surcharge = (
        _DEFAULT_SURCHARGE if any(m in lower for m in _SURCHARGE_MARKERS) else Decimal("0.00")
    )
    if surcharge > 0:
        msg = f"Адрес в зоне доставки. Потребуется доплата {surcharge} ₽ " "за удалённый район."
    else:
        msg = "Адрес в зоне доставки, доплата не требуется."

    return AddressQuote(
        ok=True,
        in_zone=True,
        surcharge=surcharge,
        message=msg,
        normalized_address=normalized,
    )


def find_slot(slot_id: str) -> DeliverySlot | None:
    for slot in DELIVERY_SLOTS:
        if slot.id == slot_id:
            return slot
    return None
