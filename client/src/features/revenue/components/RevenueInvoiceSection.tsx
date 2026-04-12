import React from 'react';
import {
  Plus,
  CheckCircle2,
  Clock,
  AlertCircle,
  XCircle,
  Loader2,
  Trash2,
  Archive,
} from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import { cn } from '../../../utils/cn';
import { dt } from '../../../utils/data-table-classes';
import type { InvoiceRead } from '../../../types/api.types';
import {
  FilterField,
  TableFilterPanel,
  filterControlClass,
} from '../../../components/TableFilterPanel/TableFilterPanel';
import type { InvoiceSubTab } from '../store/revenueStore';
import {
  formatInvoiceTotalCell,
  normInvoicePaymentStatus,
  paymentStatusColors,
  paymentStatusLabels,
  renderInvoiceRefFeesCell,
} from './revenue-invoice-display';

export type RevenueInvoiceSectionProps = {
  isAutoInvoiceTab: boolean;
  invoiceSubTab: InvoiceSubTab;
  onInvoiceSubTab: (t: InvoiceSubTab) => void;
  filteredInvoices: InvoiceRead[];
  invoices: InvoiceRead[];
  isLoading: boolean;
  invQ: string;
  setInvQ: (v: string) => void;
  invPayStatus: string;
  setInvPayStatus: (v: string) => void;
  invDateFrom: string;
  setInvDateFrom: (v: string) => void;
  invDateTo: string;
  setInvDateTo: (v: string) => void;
  invMinTotal: string;
  setInvMinTotal: (v: string) => void;
  invMaxTotal: string;
  setInvMaxTotal: (v: string) => void;
  resetInvFilters: () => void;
  invFilterCount: number;
  onOpenCreateInvoice: () => void;
  onOpenPayment: (inv: InvoiceRead) => void;
  onDeleteInvoice: (id: string | number) => void;
};

export const RevenueInvoiceSection: React.FC<RevenueInvoiceSectionProps> = ({
  isAutoInvoiceTab,
  invoiceSubTab,
  onInvoiceSubTab,
  filteredInvoices,
  invoices,
  isLoading,
  invQ,
  setInvQ,
  invPayStatus,
  setInvPayStatus,
  invDateFrom,
  setInvDateFrom,
  invDateTo,
  setInvDateTo,
  invMinTotal,
  setInvMinTotal,
  invMaxTotal,
  setInvMaxTotal,
  resetInvFilters,
  invFilterCount,
  onOpenCreateInvoice,
  onOpenPayment,
  onDeleteInvoice,
}) => {
  const invoiceTableColSpan =
    8 + (invoiceSubTab === 'trash' ? 1 : 0) + (isAutoInvoiceTab ? 2 : 0);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap gap-1 bg-gray-100 dark:bg-white/5 p-1 rounded-xl w-fit">
          <button
            type="button"
            onClick={() => onInvoiceSubTab('pending')}
            className={cn(
              'px-4 py-2 rounded-lg text-[10px] font-bold uppercase tracking-widest transition-all flex items-center gap-2',
              invoiceSubTab === 'pending'
                ? 'bg-white dark:bg-blue-600 text-blue-600 dark:text-white shadow-sm'
                : 'text-gray-500 hover:text-gray-900 dark:hover:text-white',
            )}
          >
            <Clock className="w-3.5 h-3.5" />
            Chờ thanh toán
          </button>
          <button
            type="button"
            onClick={() => onInvoiceSubTab('paid')}
            className={cn(
              'px-4 py-2 rounded-lg text-[10px] font-bold uppercase tracking-widest transition-all flex items-center gap-2',
              invoiceSubTab === 'paid'
                ? 'bg-white dark:bg-blue-600 text-blue-600 dark:text-white shadow-sm'
                : 'text-gray-500 hover:text-gray-900 dark:hover:text-white',
            )}
          >
            <CheckCircle2 className="w-3.5 h-3.5" />
            Đã thanh toán
          </button>
          <button
            type="button"
            onClick={() => onInvoiceSubTab('trash')}
            className={cn(
              'px-4 py-2 rounded-lg text-[10px] font-bold uppercase tracking-widest transition-all flex items-center gap-2',
              invoiceSubTab === 'trash'
                ? 'bg-white dark:bg-blue-600 text-blue-600 dark:text-white shadow-sm'
                : 'text-gray-500 hover:text-gray-900 dark:hover:text-white',
            )}
          >
            <Archive className="w-3.5 h-3.5" />
            Đã xóa
          </button>
        </div>

        <TableFilterPanel onReset={resetInvFilters} activeCount={invFilterCount}>
          <FilterField label="Từ khóa (số HĐ / mã đơn / trạng thái raw)">
            <input
              type="text"
              value={invQ}
              onChange={(e) => setInvQ(e.target.value)}
              placeholder="Lọc nhanh..."
              className={filterControlClass}
            />
          </FilterField>
          <FilterField label="Trạng thái thanh toán">
            <select
              value={invPayStatus}
              onChange={(e) => setInvPayStatus(e.target.value)}
              className={filterControlClass}
            >
              <option value="">Theo tab hiện tại (không siết thêm)</option>
              <option value="PAID">PAID</option>
              <option value="PARTIAL">PARTIAL</option>
              <option value="UNPAID">UNPAID</option>
              <option value="OVERDUE">OVERDUE</option>
              <option value="CANCELLED">CANCELLED</option>
            </select>
          </FilterField>
          <FilterField label="Từ ngày (tạo HĐ)">
            <input
              type="date"
              value={invDateFrom}
              onChange={(e) => setInvDateFrom(e.target.value)}
              className={filterControlClass}
            />
          </FilterField>
          <FilterField label="Đến ngày">
            <input
              type="date"
              value={invDateTo}
              onChange={(e) => setInvDateTo(e.target.value)}
              className={filterControlClass}
            />
          </FilterField>
          <FilterField label="Tổng tiền tối thiểu (₫)">
            <input
              type="number"
              min={0}
              value={invMinTotal}
              onChange={(e) => setInvMinTotal(e.target.value)}
              className={filterControlClass}
            />
          </FilterField>
          <FilterField label="Tổng tiền tối đa (₫)">
            <input
              type="number"
              min={0}
              value={invMaxTotal}
              onChange={(e) => setInvMaxTotal(e.target.value)}
              className={filterControlClass}
            />
          </FilterField>
        </TableFilterPanel>

        {!isAutoInvoiceTab && (
          <div className="flex justify-end">
            <Button
              type="button"
              onClick={onOpenCreateInvoice}
              className="bg-blue-600 hover:bg-blue-700 text-white shadow-lg shadow-blue-600/20"
            >
              <Plus className="w-4 h-4 mr-2" />
              Tạo Hóa Đơn
            </Button>
          </div>
        )}
      </div>

      <div className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 rounded-2xl shadow-2xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className={dt.headRow}>
                <th className={dt.pad}>Số Hóa Đơn</th>
                <th className={dt.pad}>Mã Đơn Hàng</th>
                {isAutoInvoiceTab && (
                  <>
                    <th className={dt.pad}>Detection</th>
                    <th className={dt.pad}>Tàu (ID)</th>
                  </>
                )}
                <th className={dt.pad}>Thời Gian</th>
                {invoiceSubTab === 'trash' && <th className={dt.pad}>Ngày xóa</th>}
                <th className={dt.pad}>Trạng Thái</th>
                <th className={dt.pad}>Phí tham chiếu (đơn vị: giờ / tháng / năm)</th>
                <th className={dt.pad}>Tổng Tiền</th>
                <th className={dt.pad}>Được tạo bởi</th>
                <th className={cn(dt.pad, 'text-right')}>Thao Tác</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-white/5">
              {isLoading && invoices.length === 0 ? (
                <tr>
                  <td colSpan={invoiceTableColSpan} className={cn(dt.pad, 'py-12 text-center')}>
                    <Loader2 className="w-8 h-8 animate-spin text-blue-500 mx-auto" />
                  </td>
                </tr>
              ) : filteredInvoices.length > 0 ? (
                filteredInvoices.map((inv: InvoiceRead) => {
                  const payKey = normInvoicePaymentStatus(inv.payment_status);
                  return (
                    <tr
                      key={inv.id}
                      className="hover:bg-gray-50 dark:hover:bg-white/[0.02] transition-colors"
                    >
                      <td className={cn(dt.pad, dt.monoAccent)}>{inv.invoice_number}</td>
                      <td className={cn(dt.pad, dt.mono, 'text-gray-500 dark:text-gray-400')}>
                        {inv.order_id != null && inv.order_id !== '' ? String(inv.order_id) : '—'}
                      </td>
                      {isAutoInvoiceTab && (
                        <>
                          <td className={cn(dt.pad, dt.mono, 'text-gray-500 dark:text-gray-400')}>
                            {inv.detection_id != null && inv.detection_id !== ''
                              ? String(inv.detection_id)
                              : '—'}
                          </td>
                          <td className={cn(dt.pad, dt.mono, 'text-gray-500 dark:text-gray-400')}>
                            {inv.vessel_id != null && inv.vessel_id !== '' ? `#${inv.vessel_id}` : '—'}
                          </td>
                        </>
                      )}
                      <td className={cn(dt.pad, dt.mono, 'text-gray-500 dark:text-gray-400')}>
                        {new Date(inv.created_at).toLocaleString('vi-VN')}
                      </td>
                      {invoiceSubTab === 'trash' && (
                        <td className={cn(dt.pad, dt.mono, 'text-gray-500 dark:text-gray-400')}>
                          {inv.deleted_at ? new Date(inv.deleted_at).toLocaleString('vi-VN') : '—'}
                        </td>
                      )}
                      <td className={dt.pad}>
                        <span
                          className={cn(
                            'inline-flex items-center px-2.5 py-1 rounded-full border',
                            dt.badge,
                            paymentStatusColors[payKey] || paymentStatusColors.unpaid,
                          )}
                        >
                          {payKey === 'paid' && (
                            <CheckCircle2 className="w-3.5 h-3.5 mr-1 shrink-0" />
                          )}
                          {payKey === 'partial' && <Clock className="w-3.5 h-3.5 mr-1 shrink-0" />}
                          {(payKey === 'unpaid' || payKey === 'overdue') && (
                            <AlertCircle className="w-3.5 h-3.5 mr-1 shrink-0" />
                          )}
                          {payKey === 'cancelled' && <XCircle className="w-3.5 h-3.5 mr-1 shrink-0" />}
                          {paymentStatusLabels[payKey] || inv.payment_status}
                        </span>
                      </td>
                      <td className={dt.pad}>{renderInvoiceRefFeesCell(inv)}</td>
                      <td className={cn(dt.pad, dt.mono, 'font-bold text-gray-900 dark:text-white')}>
                        {formatInvoiceTotalCell(inv, isAutoInvoiceTab)}
                      </td>
                      <td
                        className={cn(dt.pad, dt.bodyMuted, 'max-w-[10rem] truncate')}
                        title={inv.created_by_label ?? ''}
                      >
                        {inv.created_by_label ?? '—'}
                      </td>
                      <td className={cn(dt.pad, 'text-right')}>
                        {invoiceSubTab === 'trash' ? (
                          <span className={cn(dt.meta, 'normal-case')}>—</span>
                        ) : (
                          <div className="flex flex-col items-end gap-2">
                            {payKey !== 'paid' && (
                              <button
                                type="button"
                                onClick={() => onOpenPayment(inv)}
                                className={cn(
                                  dt.action,
                                  'text-blue-600 hover:text-blue-500 dark:text-blue-400',
                                )}
                              >
                                Thanh toán
                              </button>
                            )}
                            <button
                              type="button"
                              onClick={() => onDeleteInvoice(inv.id)}
                              disabled={isLoading}
                              className={cn(
                                dt.action,
                                'inline-flex items-center gap-1 text-red-600 hover:text-red-500 dark:text-red-400 disabled:opacity-50',
                              )}
                            >
                              <Trash2 className="w-3.5 h-3.5 shrink-0" />
                              Xóa
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td
                    colSpan={invoiceTableColSpan}
                    className={cn(dt.pad, 'py-12 text-center font-mono uppercase tracking-wide', dt.empty)}
                  >
                    {invoices.length === 0
                      ? invoiceSubTab === 'pending'
                        ? isAutoInvoiceTab
                          ? 'Chưa có hóa đơn tự động chờ thanh toán'
                          : 'Không có hóa đơn chờ thanh toán'
                        : invoiceSubTab === 'paid'
                          ? isAutoInvoiceTab
                            ? 'Chưa có hóa đơn tự động đã thanh toán'
                            : 'Không có hóa đơn đã thanh toán'
                          : isAutoInvoiceTab
                            ? 'Chưa có hóa đơn tự động đã xóa'
                            : 'Chưa có hóa đơn đã xóa'
                      : 'Không có hóa đơn khớp bộ lọc'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
