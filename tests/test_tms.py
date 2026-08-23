"""Тесты mock TMS."""

from delivery_bot.integrations.tms.mock import MockTmsService


def test_tracking_delivering_has_gps() -> None:
    tms = MockTmsService()
    point = tms.tracking_for(
        order_id="ORD-1001",
        status="delivering",
        courier_name="Иван Петров",
        courier_phone="+79001112233",
        eta_minutes=25,
    )
    assert point.gps_available is True
    assert point.courier_lat is not None
    assert point.courier_lon is not None
    assert point.courier_name == "Иван Петров"


def test_tracking_paid_no_gps() -> None:
    tms = MockTmsService()
    point = tms.tracking_for(
        order_id="ORD-1002",
        status="paid",
        courier_name=None,
        courier_phone=None,
        eta_minutes=90,
    )
    assert point.gps_available is False
    assert point.courier_lat is None
    assert "назначен" in (point.message or "").lower() or "геолокац" in (
        point.message or ""
    ).lower()
