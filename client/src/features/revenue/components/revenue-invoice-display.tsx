import { cn } from '../../../utils/cn';
import { dt } from '../../../utils/data-table-classes';
import type { InvoiceRead } from '../../../types/api.types';

export { OverBerthLimitBadge } from '../../../components/Badge/OverBerthLimitBadge';
export { OutsideHoursBadge } from '../../../components/Badge/OutsideHoursBadge';

/** Số phút neo đậu từ API (seconds hoặc hours); null nếu không có dữ liệu. */
export function getInvoiceBerthMinutes(inv: {
  berth_duration_seconds?: number | null;
  berth_duration_hours?: number | string | null;
}): number | null {
  let totalSeconds = Number(inv.berth_duration_seconds ?? NaN);
  if (!Number.isFinite(totalSeconds) || totalSeconds <= 0) {
    const h = Number(inv.berth_duration_hours ?? NaN);
    if (Number.isFinite(h) && h > 0) {
      totalSeconds = Math.round(h * 3600);
    }
  }
  if (!Number.isFinite(totalSeconds) || totalSeconds <= 0) {
    return null;
  }
  return totalSeconds / 60;
}

export function formatInvoiceBerthDurationLabel(inv: {
  berth_duration_seconds?: number | null;
  berth_duration_hours?: number | string | null;
}): string {
  const berthMinutes = getInvoiceBerthMinutes(inv);
  if (berthMinutes === null) {
    return '—';
  }
  const totalSeconds = Math.round(berthMinutes * 60);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes} phút ${seconds} giây`;
}

export function normInvoicePaymentStatus(
  status: string,
): 'paid' | 'partial' | 'unpaid' | 'overdue' | 'cancelled' {
  const s = status.toUpperCase();
  if (s === 'PAID') return 'paid';
  if (s === 'PARTIAL') return 'partial';
  if (s === 'OVERDUE') return 'overdue';
  if (s === 'CANCELLED') return 'cancelled';
  return 'unpaid';
}

export function isInvoicePayable(inv: Pick<InvoiceRead, 'payment_status'>): boolean {
  return normInvoicePaymentStatus(inv.payment_status) !== 'paid';
}

export type InvoiceAmountFields = Pick<
  InvoiceRead,
  'subtotal' | 'tax_amount' | 'total_amount' | 'discount_amount' | 'discount_status'
>;

export function getInvoiceDiscountStatus(
  inv: Pick<InvoiceRead, 'discount_status'>,
): 'none' | 'pending' | 'approved' | 'rejected' {
  const raw = String(inv.discount_status ?? 'none').toLowerCase();
  if (raw === 'pending' || raw === 'approved' || raw === 'rejected') {
    return raw;
  }
  return 'none';
}

export function getInvoiceApprovedDiscount(
  inv: Pick<InvoiceRead, 'discount_amount' | 'discount_status'>,
): number {
  if (getInvoiceDiscountStatus(inv) !== 'approved') {
    return 0;
  }
  const amount = Number(inv.discount_amount ?? 0);
  return Number.isFinite(amount) ? Math.max(0, amount) : 0;
}

export function getInvoiceRequestedDiscount(
  inv: Pick<InvoiceRead, 'discount_requested_amount'>,
): number {
  const amount = Number(inv.discount_requested_amount ?? 0);
  return Number.isFinite(amount) ? Math.max(0, amount) : 0;
}

export function getInvoiceGrossAmount(inv: InvoiceAmountFields): number {
  const sub = Number(inv.subtotal ?? 0);
  const tax = Number(inv.tax_amount ?? 0);
  const fromItems = (Number.isFinite(sub) ? sub : 0) + (Number.isFinite(tax) ? tax : 0);
  if (fromItems > 0) {
    return fromItems;
  }
  const total = Number(inv.total_amount ?? 0);
  const disc = Number(inv.discount_amount ?? 0);
  const gross = (Number.isFinite(total) ? total : 0) + (Number.isFinite(disc) ? disc : 0);
  return Math.max(0, gross);
}

export function getInvoiceNetAmount(inv: InvoiceAmountFields): number {
  const gross = getInvoiceGrossAmount(inv);
  const discount = getInvoiceApprovedDiscount(inv);
  return Math.max(0, gross - Math.min(discount, gross));
}

export function getInvoiceDisplayAmount(inv: InvoiceAmountFields): number {
  const stored = Number(inv.total_amount ?? 0);
  if (Number.isFinite(stored) && stored > 0) {
    return stored;
  }
  return getInvoiceNetAmount(inv);
}

export function sumInvoiceDisplayAmounts(invoices: InvoiceAmountFields[]): number {
  return invoices.reduce((acc, inv) => acc + getInvoiceDisplayAmount(inv), 0);
}

export function formatMoney(value: number | string) {
  const n = Number(value);
  return Number.isFinite(n) ? n.toLocaleString('vi-VN') : String(value);
}

export function renderInvoiceRefFeesCell(inv: InvoiceRead) {
  if (!inv.items?.length) {
    return '—';
  }

  return (
    <ul className="m-0 min-w-0 list-none space-y-0.5 p-0">
      {inv.items.map((it, idx) => {
        const unit = it.fee_config?.unit ?? null;
        const unitLabel =
          unit === 'per_hour'
            ? '/ giờ'
            : unit === 'per_month'
              ? '/ tháng'
              : unit === 'per_year'
                ? '/ năm'
                : unit === 'per_berth_visit'
                  ? '/ lượt'
                  : '';
        const price = Number(it.unit_price ?? 0);
        return (
          <li key={it.id ?? idx} className="text-xs leading-snug text-gray-600 dark:text-gray-300">
            <span className="font-medium text-gray-800 dark:text-gray-200">
              {(it.fee_config?.fee_name || 'Dòng phí').trim()}:
            </span>{' '}
            {Number.isFinite(price) ? `${price.toLocaleString('vi-VN')} ₫${unitLabel}` : '—'}
          </li>
        );
      })}
    </ul>
  );
}

export const paymentStatusColors: Record<string, string> = {
  paid: 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20',
  partial: 'text-blue-500 bg-blue-500/10 border-blue-500/20',
  unpaid: 'text-amber-500 bg-amber-500/10 border-amber-500/20',
  overdue: 'text-orange-600 bg-orange-500/10 border-orange-500/25',
  cancelled: 'text-gray-500 bg-gray-500/10 border-gray-500/20',
};

export const paymentStatusLabels: Record<string, string> = {
  paid: 'Đã Thanh Toán',
  partial: 'Thanh Toán Một Phần',
  unpaid: 'Chưa Thanh Toán',
  overdue: 'Quá Hạn',
  cancelled: 'Đã Hủy',
};

export function formatInvoiceTotalCell(inv: InvoiceRead, aiTab: boolean) {
  const gross = getInvoiceGrossAmount(inv);
  const net = getInvoiceNetAmount(inv);
  const status = getInvoiceDiscountStatus(inv);
  const pending = getInvoiceRequestedDiscount(inv);
  if (aiTab && gross <= 0 && net <= 0) {
    return <span className={cn(dt.bodyMuted)}>—</span>;
  }
  return (
    <>
      {formatMoney(net)} ₫
      {status === 'pending' && pending > 0 ? (
        <span className="mt-0.5 block text-[10px] font-medium text-amber-600 dark:text-amber-400">
          Chờ duyệt: {formatMoney(pending)} ₫
        </span>
      ) : null}
    </>
  );
}
