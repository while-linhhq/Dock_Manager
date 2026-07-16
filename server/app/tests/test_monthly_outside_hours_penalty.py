from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import app.main  # noqa: F401 — initialize service imports in app order
import pytest

from app.models.detection import Detection
from app.models.fee import FeeConfig
from app.models.vessel import Vessel
from app.schemas.fee import FeeConfigCreate, _validate_fee_scope
from app.schemas.invoice import InvoiceItemCreate
from app.services.fee_penalty_service import build_penalty_items
from app.services.outside_hours_stats_service import _vn_date


VN_TZ = ZoneInfo('Asia/Ho_Chi_Minh')
MONDAY_8_TO_20 = {
    'mon': {'open': '08:00', 'close': '20:00'},
}


def test_naive_database_timestamp_is_interpreted_as_utc_for_vietnam_date():
    # 18:30 UTC = 01:30 next day in Vietnam.
    naive_utc = datetime(2026, 7, 1, 18, 30)

    assert _vn_date(naive_utc) == date(2026, 7, 2)
    assert _vn_date(naive_utc.replace(tzinfo=timezone.utc)) == date(2026, 7, 2)


def test_invoice_item_derives_amount_for_database_write():
    item = InvoiceItemCreate(quantity=Decimal('1'), unit_price=Decimal('1000000'))

    assert item.amount == Decimal('1000000.00')


def _detection(start_hour: int, end_hour: int, end_minute: int = 0) -> Detection:
    return Detection(
        id=999_001,
        start_time=datetime(2026, 7, 13, start_hour, 0, tzinfo=VN_TZ),
        end_time=datetime(2026, 7, 13, end_hour, end_minute, tzinfo=VN_TZ),
        berth_in_time=datetime(2026, 7, 13, start_hour, 0, tzinfo=VN_TZ),
        berth_out_time=datetime(2026, 7, 13, end_hour, end_minute, tzinfo=VN_TZ),
    )


def test_monthly_fractional_hours_preserve_quantity_and_unit_rate():
    vessel = Vessel(id=999_007, ship_id='TEST-MONTHLY-FRACTION', classification='monthly')
    items = build_penalty_items(
        None,
        detection=_detection(8, 21, 30),
        vessel=vessel,
        fees=[_fee(flat=None, per_hour=Decimal('1000000'))],
    )

    assert len(items) == 1
    assert items[0].quantity == Decimal('1.5')
    assert items[0].unit_price == Decimal('1000000.00')
    assert items[0].amount == Decimal('1500000.00')


def _fee(*, flat: Decimal | None, per_hour: Decimal | None) -> FeeConfig:
    return FeeConfig(
        id=999_002,
        fee_name='Phí tàu tháng',
        base_fee=Decimal('0'),
        unit='per_month',
        outside_hours_penalty_amount=flat,
        outside_hours_penalty_per_hour=per_hour,
        operating_hours=MONDAY_8_TO_20,
    )


def test_monthly_vessel_charges_only_per_hour_after_allowed_time():
    vessel = Vessel(id=999_003, ship_id='TEST-MONTHLY', classification='monthly')
    items = build_penalty_items(
        None,
        detection=_detection(20, 21),
        vessel=vessel,
        fees=[_fee(flat=Decimal('30000'), per_hour=Decimal('1000000'))],
    )

    assert len(items) == 1
    assert items[0].quantity == Decimal('1')
    assert items[0].unit_price == Decimal('1000000.00')
    assert '1.00 giờ ngoài khung' in (items[0].description or '')


def test_monthly_legacy_flat_value_is_treated_as_hourly_rate():
    vessel = Vessel(id=999_006, ship_id='TEST-MONTHLY-LEGACY', classification='monthly')
    items = build_penalty_items(
        None,
        detection=_detection(8, 21),
        vessel=vessel,
        fees=[_fee(flat=Decimal('1000000'), per_hour=None)],
    )

    assert len(items) == 1
    assert items[0].unit_price == Decimal('1000000.00')
    assert '1.00 giờ ngoài khung' in (items[0].description or '')


def test_spot_vessel_keeps_flat_per_visit_penalty():
    vessel = Vessel(id=999_004, ship_id='TEST-SPOT', classification='spot')
    items = build_penalty_items(
        None,
        detection=_detection(7, 8),
        vessel=vessel,
        fees=[_fee(flat=Decimal('30000'), per_hour=Decimal('1000000'))],
    )

    assert len(items) == 1
    assert items[0].unit_price == Decimal('30000')
    assert 'theo giờ' not in (items[0].description or '')


def test_monthly_per_hour_rate_requires_operating_hours():
    with pytest.raises(ValueError, match='outside_hours_penalty_per_hour requires operating_hours'):
        FeeConfigCreate(
            vessel_type_id=999_005,
            fee_name='Phí tàu tháng',
            base_fee=Decimal('0'),
            unit='per_month',
            outside_hours_penalty_per_hour=Decimal('1000000'),
            operating_hours=None,
        )


def test_fee_scope_rejects_both_or_neither_scope():
    with pytest.raises(ValueError, match='chính xác một phạm vi'):
        _validate_fee_scope(vessel_id=1, vessel_type_id=2)
    with pytest.raises(ValueError, match='chính xác một phạm vi'):
        _validate_fee_scope(vessel_id=None, vessel_type_id=None)

    _validate_fee_scope(vessel_id=1, vessel_type_id=None)
    _validate_fee_scope(vessel_id=None, vessel_type_id=2)
