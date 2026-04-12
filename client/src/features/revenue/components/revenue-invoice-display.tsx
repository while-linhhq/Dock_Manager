import React from 'react';
import { cn } from '../../../utils/cn';
import { dt } from '../../../utils/data-table-classes';
import { formatFeeConfigDisplay } from '../../../utils/fee-billing-unit';
import type { InvoiceRead } from '../../../types/api.types';

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

export function formatMoney(value: number | string) {
  const n = Number(value);
  return Number.isFinite(n) ? n.toLocaleString('vi-VN') : String(value);
}

export function renderInvoiceRefFeesCell(inv: InvoiceRead) {
  if (!inv.items?.length) {
    return '—';
  }
  return (
    <ul className="m-0 max-w-[14rem] list-none space-y-1 p-0">
      {inv.items.map((it, idx) => {
        const title = (it.description || it.fee_config?.fee_name || 'Dòng phí').trim();
        return (
          <li key={it.id ?? idx} className={cn(dt.bodyMuted, 'leading-snug')}>
            <span className="font-medium text-gray-800 dark:text-gray-200">{title}:</span>{' '}
            {formatFeeConfigDisplay(Number(it.amount ?? 0), it.fee_config?.unit ?? null)}
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
  const n = Number(inv.total_amount ?? 0);
  if (aiTab && n === 0) {
    return <span className={cn(dt.bodyMuted)}>—</span>;
  }
  return <>{formatMoney(inv.total_amount)} ₫</>;
}
