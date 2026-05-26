from typing import Optional

FEE_BILLING_UNITS = frozenset({'per_hour', 'per_month', 'per_year', 'per_berth_visit', 'none'})

_FEE_BILLING_UNIT_LABELS = {
    'per_hour': 'Phí theo giờ',
    'per_month': 'Phí theo tháng',
    'per_year': 'Phí theo năm',
    'per_berth_visit': 'Phí theo lượt đậu',
    'none': 'Không thu phí (tàu công ty)',
}


def normalize_fee_billing_unit(value: Optional[str]) -> str:
    u = (value or '').strip().lower()
    if u in FEE_BILLING_UNITS:
        return u
    return 'per_month'


def fee_billing_unit_label(unit: Optional[str]) -> str:
    normalized = normalize_fee_billing_unit(unit)
    return _FEE_BILLING_UNIT_LABELS[normalized]
