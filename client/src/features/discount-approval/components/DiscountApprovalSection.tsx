import React, { useState } from 'react';
import { Check, Loader2, X } from 'lucide-react';
import { cn } from '../../../utils/cn';
import { dt } from '../../../utils/data-table-classes';
import { formatDateTimeVN } from '../../../utils/date-time';
import type { InvoiceRead } from '../../../types/api.types';
import {
  formatMoney,
  getInvoiceGrossAmount,
} from '../../revenue/components/revenue-invoice-display';
import type { DiscountRequestStatus } from '../services/discountApprovalApi';
import { DiscountRejectModal } from './DiscountRejectModal';

const th = 'px-2.5 py-2 text-[11px] font-semibold text-gray-500 dark:text-gray-400 whitespace-nowrap';
const td = 'px-2.5 py-2 text-xs whitespace-nowrap align-middle';

export type DiscountApprovalSectionProps = {
  statusTab: DiscountRequestStatus;
  onStatusTab: (tab: DiscountRequestStatus) => void;
  requests: InvoiceRead[];
  isLoading: boolean;
  onApprove: (id: string | number) => Promise<void>;
  onReject: (id: string | number, reason?: string) => Promise<void>;
};

export const DiscountApprovalSection: React.FC<DiscountApprovalSectionProps> = ({
  statusTab,
  onStatusTab,
  requests,
  isLoading,
  onApprove,
  onReject,
}) => {
  const [busyId, setBusyId] = useState<string | number | null>(null);
  const [rejectTarget, setRejectTarget] = useState<InvoiceRead | null>(null);

  const handleApprove = async (inv: InvoiceRead) => {
    setBusyId(inv.id);
    try {
      await onApprove(inv.id);
    } finally {
      setBusyId(null);
    }
  };

  const handleRejectConfirm = async (reason: string) => {
    if (!rejectTarget) {
      return;
    }
    setBusyId(rejectTarget.id);
    try {
      await onReject(rejectTarget.id, reason);
      setRejectTarget(null);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-1 bg-gray-100 dark:bg-white/5 p-1 rounded-xl w-fit">
        {(
          [
            { key: 'pending' as const, label: 'Chờ duyệt' },
            { key: 'approved' as const, label: 'Đã duyệt' },
            { key: 'rejected' as const, label: 'Từ chối' },
          ] as const
        ).map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => onStatusTab(tab.key)}
            className={cn(
              'px-4 py-2 rounded-lg text-[10px] font-bold uppercase tracking-widest transition-all',
              statusTab === tab.key
                ? 'bg-white dark:bg-blue-600 text-blue-600 dark:text-white shadow-sm'
                : 'text-gray-500 hover:text-gray-900 dark:hover:text-white',
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 rounded-2xl shadow-2xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[880px] text-left border-collapse">
            <thead>
              <tr className={cn(dt.headRow, 'text-[11px] tracking-normal normal-case')}>
                <th className={cn(th, 'w-10 text-center')}>#</th>
                <th className={th}>Số HĐ</th>
                <th className={th}>Mã tàu</th>
                <th className={cn(th, 'text-right')}>Tổng trước giảm</th>
                <th className={cn(th, 'text-right')}>Yêu cầu giảm</th>
                <th className={th}>Ngày tạo HĐ</th>
                {statusTab !== 'pending' ? <th className={th}>Người duyệt</th> : null}
                {statusTab === 'rejected' ? <th className={th}>Lý do</th> : null}
                {statusTab === 'pending' ? (
                  <th className={cn(th, 'text-right')}>Thao tác</th>
                ) : null}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-white/5">
              {isLoading && requests.length === 0 ? (
                <tr>
                  <td colSpan={8} className={cn(td, 'py-10 text-center')}>
                    <Loader2 className="w-7 h-7 animate-spin text-blue-500 mx-auto" />
                  </td>
                </tr>
              ) : requests.length > 0 ? (
                requests.map((inv, index) => {
                  const gross = getInvoiceGrossAmount(inv);
                  const requested = Number(inv.discount_requested_amount ?? 0);
                  const isBusy = busyId != null && String(busyId) === String(inv.id);
                  return (
                    <tr key={inv.id} className="hover:bg-gray-50 dark:hover:bg-white/2">
                      <td className={cn(td, 'text-center text-gray-400 font-mono')}>{index + 1}</td>
                      <td className={cn(td, dt.monoAccent)}>{inv.invoice_number}</td>
                      <td className={cn(td, 'font-mono')}>{inv.vessel_ship_id ?? '—'}</td>
                      <td className={cn(td, 'text-right font-mono')}>{formatMoney(gross)} ₫</td>
                      <td className={cn(td, 'text-right font-mono text-rose-600 dark:text-rose-400')}>
                        {formatMoney(requested)} ₫
                      </td>
                      <td className={cn(td, 'font-mono')}>
                        {formatDateTimeVN(inv.created_at, {
                          day: '2-digit',
                          month: '2-digit',
                          year: '2-digit',
                          hour: '2-digit',
                          minute: '2-digit',
                          hour12: false,
                        })}
                      </td>
                      {statusTab !== 'pending' ? (
                        <td className={td}>{inv.discount_reviewed_by_label ?? '—'}</td>
                      ) : null}
                      {statusTab === 'rejected' ? (
                        <td className={cn(td, 'max-w-[12rem] truncate')} title={inv.discount_reject_reason ?? ''}>
                          {inv.discount_reject_reason?.trim() ? inv.discount_reject_reason : '—'}
                        </td>
                      ) : null}
                      {statusTab === 'pending' ? (
                        <td className={cn(td, 'text-right')}>
                          <div className="inline-flex items-center gap-1">
                            {isBusy ? (
                              <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
                            ) : null}
                            <button
                              type="button"
                              onClick={() => void handleApprove(inv)}
                              disabled={isLoading || isBusy}
                              className="p-1.5 rounded-md text-emerald-600 hover:bg-emerald-50 dark:text-emerald-400 dark:hover:bg-emerald-500/10 disabled:opacity-50"
                              title="Duyệt"
                              aria-label="Duyệt"
                            >
                              <Check className="h-3.5 w-3.5" />
                            </button>
                            <button
                              type="button"
                              onClick={() => setRejectTarget(inv)}
                              disabled={isLoading || isBusy}
                              className="p-1.5 rounded-md text-rose-600 hover:bg-rose-50 dark:text-rose-400 dark:hover:bg-rose-500/10 disabled:opacity-50"
                              title="Từ chối"
                              aria-label="Từ chối"
                            >
                              <X className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        </td>
                      ) : null}
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={8} className={cn(td, 'py-10 text-center text-gray-500')}>
                    Không có yêu cầu giảm giá trong tab này
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <DiscountRejectModal
        isOpen={rejectTarget != null}
        invoiceNumber={rejectTarget?.invoice_number ?? null}
        isLoading={busyId != null}
        onClose={() => setRejectTarget(null)}
        onConfirm={(reason) => void handleRejectConfirm(reason)}
      />
    </div>
  );
};
