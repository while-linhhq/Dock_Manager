export const FEE_BILLING_UNITS = ['per_hour', 'per_month', 'per_year', 'none'] as const;

export type FeeBillingUnit = (typeof FEE_BILLING_UNITS)[number];

export const FEE_BILLING_UNIT_LABELS: Record<FeeBillingUnit, string> = {
  per_hour: 'Phí theo giờ',
  per_month: 'Phí theo tháng',
  per_year: 'Phí theo năm',
  none: 'Không thu phí (tàu công ty)',
};

export const FEE_BILLING_UNIT_AMOUNT_LABELS: Record<FeeBillingUnit, string> = {
  per_hour: 'Mức phí (VNĐ / giờ)',
  per_month: 'Mức phí (VNĐ / tháng)',
  per_year: 'Mức phí (VNĐ / năm)',
  none: 'Mức phí',
};

export function normalizeFeeBillingUnit(unit: string | null | undefined): FeeBillingUnit {
  if (unit && (FEE_BILLING_UNITS as readonly string[]).includes(unit)) {
    return unit as FeeBillingUnit;
  }
  return 'per_month';
}

/** Short suffix for tables/cards (after amount). */
export function feeBillingUnitSuffix(unit: string | null | undefined): string {
  const u = normalizeFeeBillingUnit(unit);
  if (u === 'none') {
    return '';
  }
  if (u === 'per_hour') {
    return '/giờ';
  }
  if (u === 'per_month') {
    return '/tháng';
  }
  return '/năm';
}

export function formatFeeConfigDisplay(amount: number | string, unit: string | null | undefined): string {
  const u = normalizeFeeBillingUnit(unit);
  if (u === 'none') {
    return 'Không thu phí';
  }
  const n = Number(amount);
  const money = Number.isFinite(n) ? n.toLocaleString('vi-VN') : String(amount);
  return `${money} ₫${feeBillingUnitSuffix(unit)}`;
}
