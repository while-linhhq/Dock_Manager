import React from 'react';
import type { InvoiceRead } from '../../../types/api.types';
import { formatDateTimeVN } from '../../../utils/date-time';
import {
  formatInvoiceBerthDurationLabel,
  formatMoney,
  getInvoiceApprovedDiscount,
  getInvoiceDiscountStatus,
  getInvoiceGrossAmount,
  getInvoiceNetAmount,
  getInvoiceRequestedDiscount,
  renderInvoiceRefFeesCell,
} from './revenue-invoice-display';

export type InvoicePaymentSummaryProps = {
  invoice: InvoiceRead;
  showAmount?: boolean;
};

export const InvoicePaymentSummary: React.FC<InvoicePaymentSummaryProps> = ({
  invoice,
  showAmount = true,
}) => {
  const gross = getInvoiceGrossAmount(invoice);
  const discountStatus = getInvoiceDiscountStatus(invoice);
  const approvedDiscount = getInvoiceApprovedDiscount(invoice);
  const pendingDiscount = getInvoiceRequestedDiscount(invoice);
  const amount = getInvoiceNetAmount(invoice);
  const berthArrival = invoice.detection?.start_time
    ? formatDateTimeVN(invoice.detection.start_time)
    : '—';

  return (
    <div className="rounded-xl border border-gray-100 bg-gray-50 p-3 dark:border-white/5 dark:bg-white/5">
      <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">Hóa đơn</p>
      <p className="mt-1 font-mono text-sm font-bold text-gray-900 dark:text-white">
        {invoice.invoice_number}
      </p>

      <div className="mt-2 grid gap-2 text-sm sm:grid-cols-2">
        <SummaryRow label="Mã tàu" value={invoice.vessel_ship_id ?? '—'} mono />
        <SummaryRow label="Loại tàu" value={invoice.vessel_type_name ?? '—'} />
        <SummaryRow label="Thời gian cập bến" value={berthArrival} mono />
        <SummaryRow label="Neo đậu" value={formatInvoiceBerthDurationLabel(invoice)} />
      </div>

      <div className="mt-2 border-t border-gray-200/80 pt-2 dark:border-white/10">
        <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">
          Phí tham chiếu
        </p>
        <div className="mt-1 max-h-28 overflow-y-auto pr-1">{renderInvoiceRefFeesCell(invoice)}</div>
      </div>

      {showAmount ? (
        <div className="mt-3 space-y-2 border-t border-gray-200/80 pt-3 dark:border-white/10">
          {gross > 0 ? (
            <SummaryRow label="Tổng trước giảm" value={`${formatMoney(gross)} ₫`} mono />
          ) : null}
          {approvedDiscount > 0 ? (
            <SummaryRow label="Giảm giá (đã duyệt)" value={`−${formatMoney(approvedDiscount)} ₫`} mono />
          ) : null}
          {discountStatus === 'pending' && pendingDiscount > 0 ? (
            <SummaryRow
              label="Giảm giá (chờ duyệt)"
              value={`${formatMoney(pendingDiscount)} ₫ — chưa trừ`}
              mono
            />
          ) : null}
          <div>
            <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">
              Số tiền thanh toán
            </p>
            <p className="mt-1 text-lg font-bold text-blue-600 dark:text-blue-400">
              {formatMoney(amount)} ₫
            </p>
          </div>
        </div>
      ) : null}
    </div>
  );
};

function SummaryRow({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="min-w-0">
      <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">{label}</p>
      <p
        className={mono ? 'mt-0.5 truncate font-mono text-xs text-gray-800 dark:text-gray-200' : 'mt-0.5 truncate text-xs text-gray-800 dark:text-gray-200'}
        title={value}
      >
        {value}
      </p>
    </div>
  );
}
