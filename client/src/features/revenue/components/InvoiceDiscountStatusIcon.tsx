import React from 'react';
import { BadgeCheck, CircleX, Clock } from 'lucide-react';
import { cn } from '../../../utils/cn';
import type { InvoiceRead } from '../../../types/api.types';
import {
  formatMoney,
  getInvoiceApprovedDiscount,
  getInvoiceDiscountStatus,
  getInvoiceRequestedDiscount,
} from './revenue-invoice-display';

export type InvoiceDiscountStatusIconProps = {
  invoice: Pick<
    InvoiceRead,
    'discount_status' | 'discount_amount' | 'discount_requested_amount' | 'discount_reject_reason'
  >;
  className?: string;
};

export const InvoiceDiscountStatusIcon: React.FC<InvoiceDiscountStatusIconProps> = ({
  invoice,
  className,
}) => {
  const status = getInvoiceDiscountStatus(invoice);
  if (status === 'none') {
    return null;
  }

  const requested = getInvoiceRequestedDiscount(invoice);
  const approved = getInvoiceApprovedDiscount(invoice);
  const amount = status === 'approved' ? approved : requested;

  if (status !== 'rejected' && amount <= 0) {
    return null;
  }

  const config = {
    pending: {
      Icon: Clock,
      color: 'text-amber-500',
      label: `Chờ duyệt giảm ${formatMoney(amount)} ₫`,
    },
    approved: {
      Icon: BadgeCheck,
      color: 'text-emerald-500',
      label: `Đã duyệt giảm ${formatMoney(amount)} ₫`,
    },
    rejected: {
      Icon: CircleX,
      color: 'text-rose-500',
      label: invoice.discount_reject_reason?.trim()
        ? `Từ chối — ${invoice.discount_reject_reason.trim()}`
        : 'Từ chối — có thể sửa gửi lại',
    },
  }[status];

  const { Icon, color, label } = config;

  return (
    <span title={label} className={cn('inline-flex shrink-0', className)}>
      <Icon className={cn('h-3.5 w-3.5', color)} aria-label={label} />
    </span>
  );
};
