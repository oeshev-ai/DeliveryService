"""Схемы и mock TMS (координаты курьера)."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from delivery_bot.services.order_policy import OrderStatus

# Демо-координаты около адреса «Тверская / центр Москвы»
_DESTINATIONS: dict[str, tuple[float, float]] = {
    "ORD-1001": (55.7570, 37.6150),
    "ORD-1002": (55.7520, 37.5910),
    "ORD-1003": (55.7810, 37.6330),
    "ORD-1004": (55.7570, 37.6150),
    "ORD-1005": (55.7530, 37.5890),
}

# Стартовые позиции курьера (смещение от точки доставки)
_COURIER_START: dict[str, tuple[float, float]] = {
    "ORD-1001": (55.7505, 37.6010),
}


@dataclass(frozen=True, slots=True)
class TrackingPoint:
    """Снимок трекинга заказа."""

    order_id: str
    dest_lat: float
    dest_lon: float
    courier_lat: float | None
    courier_lon: float | None
    gps_available: bool
    courier_name: str | None
    courier_phone: str | None
    eta_minutes: int | None
    status: str
    message: str | None = None


class MockTmsService:
    """Имитация TMS: координаты курьера + движение к точке доставки."""

    def tracking_for(
        self,
        *,
        order_id: str,
        status: str,
        courier_name: str | None,
        courier_phone: str | None,
        eta_minutes: int | None,
    ) -> TrackingPoint:
        oid = order_id.upper()
        dest = _DESTINATIONS.get(oid, (55.7558, 37.6173))
        dest_lat, dest_lon = dest

        in_transit = status in {
            OrderStatus.HANDED_TO_COURIER.value,
            OrderStatus.DELIVERING.value,
        }

        if not in_transit or not courier_name:
            return TrackingPoint(
                order_id=oid,
                dest_lat=dest_lat,
                dest_lon=dest_lon,
                courier_lat=None,
                courier_lon=None,
                gps_available=False,
                courier_name=courier_name,
                courier_phone=courier_phone,
                eta_minutes=eta_minutes,
                status=status,
                message=(
                    "Курьер ещё не назначен."
                    if not courier_name
                    else "Геолокация доступна, когда заказ у курьера / в пути."
                ),
            )

        # ORD-1004 delivered — фиксируем на точке
        if status == OrderStatus.DELIVERED.value:
            return TrackingPoint(
                order_id=oid,
                dest_lat=dest_lat,
                dest_lon=dest_lon,
                courier_lat=dest_lat,
                courier_lon=dest_lon,
                gps_available=True,
                courier_name=courier_name,
                courier_phone=courier_phone,
                eta_minutes=0,
                status=status,
                message=None,
            )

        start = _COURIER_START.get(oid, (dest_lat - 0.012, dest_lon - 0.015))
        # Плавное движение к точке доставки по времени (цикл ~10 мин)
        phase = (time.time() % 600) / 600.0
        # лёгкое «покачивание» маршрута
        wobble = 0.0008 * math.sin(phase * math.pi * 4)
        lat = start[0] + (dest_lat - start[0]) * phase + wobble
        lon = start[1] + (dest_lon - start[1]) * phase

        return TrackingPoint(
            order_id=oid,
            dest_lat=dest_lat,
            dest_lon=dest_lon,
            courier_lat=lat,
            courier_lon=lon,
            gps_available=True,
            courier_name=courier_name,
            courier_phone=courier_phone,
            eta_minutes=eta_minutes,
            status=status,
            message=None,
        )
