import React, { useEffect, useRef, useState } from 'react';
import {
  Plus,
  CheckCircle2,
  Clock,
  Eye,
  Loader2,
  Trash2,
  Archive,
  Banknote,
  FileSpreadsheet,
} from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import { DetectionCompareModal } from '../../../components/DetectionCompareModal/DetectionCompareModal';
import { cn } from '../../../utils/cn';
import { dt } from '../../../utils/data-table-classes';
import { formatDateTimeVN } from '../../../utils/date-time';
import type { InvoiceRead, VesselRead, VesselTypeRead } from '../../../types/api.types';
import {
  FilterField,
  TableFilterPanel,
  filterControlClass,
} from '../../../components/TableFilterPanel/TableFilterPanel';
import type { InvoiceSubTab } from '../store/revenueStore';
import {
  formatInvoiceTotalCell,
  formatMoney,
  getInvoiceApprovedDiscount,
  getInvoiceDiscountStatus,
  getInvoiceGrossAmount,
  getInvoiceBerthMinutes,
  getInvoiceRequestedDiscount,
  normInvoicePaymentStatus,
  OverBerthLimitBadge,
  OutsideHoursBadge,
  paymentStatusColors,
  paymentStatusLabels,
  renderInvoiceRefFeesCell,
} from './revenue-invoice-display';
import { InvoiceDiscountStatusIcon } from './InvoiceDiscountStatusIcon';

const invTh =
  'px-2.5 py-2 text-[11px] font-semibold text-gray-500 dark:text-gray-400 whitespace-nowrap';
const invTd = 'px-2.5 py-2 text-xs whitespace-nowrap align-middle';
const invTdMono = cn(invTd, 'font-mono text-gray-600 dark:text-gray-300');

const paymentStatusShortLabels: Record<string, string> = {
  paid: 'Đã TT',
  partial: 'Một phần',
  unpaid: 'Chưa TT',
  overdue: 'Quá hạn',
  cancelled: 'Đã hủy',
};

function getInvoiceDetectionId(inv: InvoiceRead): string | number | null {
  const id = inv.detection_id ?? inv.detection?.id;
  if (id == null || id === '') {
    return null;
  }
  return id;
}

function getInvoiceShipLabel(inv: InvoiceRead, vessels: VesselRead[]): string {
  if (inv.vessel_ship_id) {
    return inv.vessel_ship_id;
  }
  const vessel = vessels.find((row) => String(row.id) === String(inv.vessel_id ?? ''));
  return vessel?.ship_id ?? '—';
}

export type RevenueInvoiceSectionProps = {
  isAutoInvoiceTab: boolean;
  invoiceSubTab: InvoiceSubTab;
  onInvoiceSubTab: (t: InvoiceSubTab) => void;
  filteredInvoices: InvoiceRead[];
  invoices: InvoiceRead[];
  isLoading: boolean;
  invQ: string;
  setInvQ: (v: string) => void;
  invMinBerthMinutes: string;
  setInvMinBerthMinutes: (v: string) => void;
  invShipIdFilter: string;
  setInvShipIdFilter: (v: string) => void;
  invVesselTypeFilter: string;
  setInvVesselTypeFilter: (v: string) => void;
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
  vessels: VesselRead[];
  vesselTypes: VesselTypeRead[];
  onOpenCreateInvoice: () => void;
  onOpenPayment: (inv: InvoiceRead) => void;
  onDeleteInvoice: (id: string | number) => void;
  onUpdateDiscount: (id: string | number, discountAmount: number) => Promise<void>;
  onUpdateNotes: (id: string | number, notes: string) => Promise<void>;
  payableCount: number;
  bulkPaymentTotal: number;
  onOpenBulkPayment: () => void;
  onExportExcel: () => void;
  isExporting: boolean;
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
  invMinBerthMinutes,
  setInvMinBerthMinutes,
  invShipIdFilter,
  setInvShipIdFilter,
  invVesselTypeFilter,
  setInvVesselTypeFilter,
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
  vessels,
  vesselTypes,
  onOpenCreateInvoice,
  onOpenPayment,
  onDeleteInvoice,
  onUpdateDiscount,
  onUpdateNotes,
  payableCount,
  bulkPaymentTotal,
  onOpenBulkPayment,
  onExportExcel,
  isExporting,
}) => {
  const [compareOpen, setCompareOpen] = useState(false);
  const [compareInvoice, setCompareInvoice] = useState<InvoiceRead | null>(null);
  const [discountDrafts, setDiscountDrafts] = useState<Record<string, string>>({});
  const [noteDrafts, setNoteDrafts] = useState<Record<string, string>>({});
  const [savingDiscountId, setSavingDiscountId] = useState<string | number | null>(null);
  const [savingNoteId, setSavingNoteId] = useState<string | number | null>(null);
  const discountSaveTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const noteSaveTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  useEffect(() => {
    const discountTimers = discountSaveTimers.current;
    const noteTimers = noteSaveTimers.current;
    return () => {
      Object.values(discountTimers).forEach((timer) => clearTimeout(timer));
      Object.values(noteTimers).forEach((timer) => clearTimeout(timer));
    };
  }, []);

  const getDiscountDraft = (inv: InvoiceRead) => {
    const key = String(inv.id);
    if (key in discountDrafts) {
      return discountDrafts[key];
    }
    const status = getInvoiceDiscountStatus(inv);
    const amount =
      status === 'approved'
        ? getInvoiceApprovedDiscount(inv)
        : getInvoiceRequestedDiscount(inv);
    return String(amount);
  };

  const clearDiscountDraft = (id: string | number) => {
    const key = String(id);
    setDiscountDrafts((prev) => {
      if (!(key in prev)) {
        return prev;
      }
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  const getDiscountValue = (inv: InvoiceRead, raw?: string) => {
    const gross = getInvoiceGrossAmount(inv);
    const parsed = Math.max(0, Math.round(Number(raw ?? getDiscountDraft(inv)) || 0));
    return Math.min(parsed, gross);
  };

  const persistDiscount = async (inv: InvoiceRead, raw?: string) => {
    const next = getDiscountValue(inv, raw);
    const status = getInvoiceDiscountStatus(inv);
    const prev =
      status === 'approved'
        ? getInvoiceApprovedDiscount(inv)
        : getInvoiceRequestedDiscount(inv);
    if (next === prev) {
      clearDiscountDraft(inv.id);
      return;
    }
    setSavingDiscountId(inv.id);
    try {
      await onUpdateDiscount(inv.id, next);
      clearDiscountDraft(inv.id);
    } finally {
      setSavingDiscountId(null);
    }
  };

  const scheduleDiscountSave = (inv: InvoiceRead, raw: string) => {
    const key = String(inv.id);
    if (discountSaveTimers.current[key]) {
      clearTimeout(discountSaveTimers.current[key]);
    }
    discountSaveTimers.current[key] = setTimeout(() => {
      delete discountSaveTimers.current[key];
      void persistDiscount(inv, raw);
    }, 250);
  };

  const handleDiscountChange = (inv: InvoiceRead, raw: string) => {
    const key = String(inv.id);
    setDiscountDrafts((prev) => ({ ...prev, [key]: raw }));
    scheduleDiscountSave(inv, raw);
  };

  const getNoteDraft = (inv: InvoiceRead) => {
    const key = String(inv.id);
    if (key in noteDrafts) {
      return noteDrafts[key];
    }
    return inv.notes ?? '';
  };

  const clearNoteDraft = (id: string | number) => {
    const key = String(id);
    setNoteDrafts((prev) => {
      if (!(key in prev)) {
        return prev;
      }
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  const persistNotes = async (inv: InvoiceRead, raw?: string) => {
    const next = (raw ?? getNoteDraft(inv)).trim();
    const prev = (inv.notes ?? '').trim();
    if (next === prev) {
      clearNoteDraft(inv.id);
      return;
    }
    setSavingNoteId(inv.id);
    try {
      await onUpdateNotes(inv.id, next);
      clearNoteDraft(inv.id);
    } finally {
      setSavingNoteId(null);
    }
  };

  const scheduleNoteSave = (inv: InvoiceRead, raw: string) => {
    const key = String(inv.id);
    if (noteSaveTimers.current[key]) {
      clearTimeout(noteSaveTimers.current[key]);
    }
    noteSaveTimers.current[key] = setTimeout(() => {
      delete noteSaveTimers.current[key];
      void persistNotes(inv, raw);
    }, 400);
  };

  const handleNoteChange = (inv: InvoiceRead, raw: string) => {
    const key = String(inv.id);
    setNoteDrafts((prev) => ({ ...prev, [key]: raw }));
    scheduleNoteSave(inv, raw);
  };

  const openCompareModal = (inv: InvoiceRead) => {
    setCompareInvoice(inv);
    setCompareOpen(true);
  };

  const formatBerthDuration = (inv: InvoiceRead) => {
    const berthMinutes = getInvoiceBerthMinutes(inv);
    if (berthMinutes === null) {
      return null;
    }
    const totalSeconds = Math.round(berthMinutes * 60);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return {
      short: `${minutes}:${String(seconds).padStart(2, '0')}`,
      full: `${minutes} phút ${seconds} giây`,
    };
  };

  const formatCompactDateTime = (value: string | null | undefined) =>
    formatDateTimeVN(value, {
      day: '2-digit',
      month: '2-digit',
      year: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });

  const invoiceTableColSpan =
    10 + (invoiceSubTab === 'trash' ? 1 : 0) + (isAutoInvoiceTab ? 1 : 0);

  const discountInputClass =
    'w-24 rounded-md border border-gray-200 bg-white px-2 py-1 text-right text-xs font-mono tabular-nums text-gray-900 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/30 dark:border-white/10 dark:bg-[#1a1a1e] dark:text-white disabled:opacity-50';
  const noteInputClass =
    'w-full min-w-[9rem] max-w-[14rem] rounded-md border border-gray-200 bg-white px-2 py-1 text-xs text-gray-900 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/30 dark:border-white/10 dark:bg-[#1a1a1e] dark:text-white disabled:opacity-50 resize-y min-h-[2rem] max-h-20';

  return (
    <div className="space-y-4">
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
          <FilterField label="Từ khóa (số HĐ / mã đơn / mã tàu)">
            <input
              type="text"
              value={invQ}
              onChange={(e) => setInvQ(e.target.value)}
              placeholder="VD: HD-001, SG-8176..."
              className={filterControlClass}
            />
          </FilterField>
          <FilterField label="Thời gian neo đậu tối thiểu (phút)">
            <input
              type="number"
              min={0}
              step={1}
              value={invMinBerthMinutes}
              onChange={(e) => setInvMinBerthMinutes(e.target.value)}
              placeholder="VD: 30"
              className={filterControlClass}
            />
          </FilterField>
          <FilterField label="Mã tàu">
            <select
              value={invShipIdFilter}
              onChange={(e) => setInvShipIdFilter(e.target.value)}
              className={filterControlClass}
            >
              <option value="">Tất cả</option>
              {vessels.map((vessel) => (
                <option key={vessel.id} value={String(vessel.id)}>
                  {vessel.ship_id}
                </option>
              ))}
            </select>
          </FilterField>
          <FilterField label="Loại tàu">
            <select
              value={invVesselTypeFilter}
              onChange={(e) => setInvVesselTypeFilter(e.target.value)}
              className={filterControlClass}
            >
              <option value="">Tất cả</option>
              {vesselTypes.map((type) => (
                <option key={type.id} value={String(type.id)}>
                  {type.type_name}
                </option>
              ))}
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

        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">
            Tab hiện tại:{' '}
            <span className="font-semibold text-gray-700 dark:text-gray-200">{invoices.length}</span>{' '}
            hóa đơn
            {filteredInvoices.length !== invoices.length ? (
              <>
                {' '}
                · Khớp filter:{' '}
                <span className="font-semibold">{filteredInvoices.length}</span>
              </>
            ) : null}
          </p>
          <Button
            type="button"
            variant="outline"
            onClick={onExportExcel}
            disabled={isExporting}
            className="border-emerald-500/50 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-500/10 shrink-0 disabled:opacity-50"
          >
            {isExporting ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <FileSpreadsheet className="w-4 h-4 mr-2" />
            )}
            Xuất Excel
          </Button>
        </div>

        {invoiceSubTab === 'pending' && (
          <div
            className={cn(
              'flex flex-wrap items-center gap-3',
              !isAutoInvoiceTab ? 'justify-between' : 'justify-start',
            )}
          >
            <Button
              type="button"
              onClick={onOpenBulkPayment}
              disabled={payableCount === 0 || isLoading}
              className="bg-emerald-600 hover:bg-emerald-700 text-white shadow-lg shadow-emerald-600/20 disabled:opacity-50"
            >
              <Banknote className="w-4 h-4 mr-2" />
              Thanh toán tất cả ({payableCount}) — {formatMoney(bulkPaymentTotal)} ₫
            </Button>
            {!isAutoInvoiceTab && (
              <Button
                type="button"
                onClick={onOpenCreateInvoice}
                className="bg-blue-600 hover:bg-blue-700 text-white shadow-lg shadow-blue-600/20"
              >
                <Plus className="w-4 h-4 mr-2" />
                Tạo Hóa Đơn
              </Button>
            )}
          </div>
        )}
      </div>

      <div className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 rounded-2xl shadow-2xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[920px] text-left border-collapse">
            <thead>
              <tr className={cn(dt.headRow, 'text-[11px] tracking-normal normal-case')}>
                <th className={cn(invTh, 'w-10 text-center')}>#</th>
                <th className={invTh}>Số HĐ</th>
                <th className={invTh}>{isAutoInvoiceTab ? 'Mã tàu' : 'Mã đơn'}</th>
                {isAutoInvoiceTab && <th className={invTh}>Neo đậu</th>}
                <th className={invTh}>Ngày tạo</th>
                {invoiceSubTab === 'trash' && <th className={invTh}>Ngày xóa</th>}
                <th className={invTh}>Trạng thái</th>
                <th className={invTh}>Phí</th>
                <th className={invTh}>{isAutoInvoiceTab ? 'Loại tàu' : 'Tạo bởi'}</th>
                <th className={cn(invTh, 'text-right min-w-[8.5rem]')}>Tổng tiền</th>
                <th className={cn(invTh, 'min-w-[9rem]')}>Ghi chú</th>
                <th className={cn(invTh, 'w-24 text-right')}>Thao tác</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-white/5">
              {isLoading && invoices.length === 0 ? (
                <tr>
                  <td colSpan={invoiceTableColSpan} className={cn(invTd, 'py-10 text-center')}>
                    <Loader2 className="w-7 h-7 animate-spin text-blue-500 mx-auto" />
                  </td>
                </tr>
              ) : filteredInvoices.length > 0 ? (
                filteredInvoices.map((inv: InvoiceRead, rowIndex) => {
                  const payKey = normInvoicePaymentStatus(inv.payment_status);
                  const berthDuration = formatBerthDuration(inv);
                  return (
                    <tr
                      key={inv.id}
                      className="hover:bg-gray-50 dark:hover:bg-white/2 transition-colors"
                    >
                      <td className={cn(invTd, 'text-center text-gray-400 font-mono tabular-nums')}>
                        {rowIndex + 1}
                      </td>
                      <td className={cn(invTd, dt.monoAccent, 'max-w-[8rem]')}>
                        <div className="flex items-center gap-1.5 min-w-0">
                          <span className="truncate" title={inv.invoice_number}>
                            {inv.invoice_number}
                          </span>
                          {isAutoInvoiceTab ? <InvoiceDiscountStatusIcon invoice={inv} /> : null}
                          {inv.is_over_berth_limit ? (
                            <OverBerthLimitBadge className="shrink-0 px-1.5 text-[8px] tracking-wide" />
                          ) : null}
                          {isAutoInvoiceTab && inv.is_outside_operating_hours ? (
                            <OutsideHoursBadge className="shrink-0 px-1.5 text-[8px] tracking-wide" />
                          ) : null}
                        </div>
                      </td>
                      <td className={invTdMono}>
                        {isAutoInvoiceTab
                          ? (inv.vessel_ship_id ?? '—')
                          : inv.order_id != null && inv.order_id !== ''
                            ? String(inv.order_id)
                            : '—'}
                      </td>
                      {isAutoInvoiceTab && (
                        <td
                          className={invTdMono}
                          title={berthDuration?.full}
                        >
                          {berthDuration?.short ?? '—'}
                        </td>
                      )}
                      <td className={invTdMono} title={formatDateTimeVN(inv.created_at)}>
                        {formatCompactDateTime(inv.created_at)}
                      </td>
                      {invoiceSubTab === 'trash' && (
                        <td
                          className={invTdMono}
                          title={inv.deleted_at ? formatDateTimeVN(inv.deleted_at) : undefined}
                        >
                          {inv.deleted_at ? formatCompactDateTime(inv.deleted_at) : '—'}
                        </td>
                      )}
                      <td className={invTd}>
                        <span
                          className={cn(
                            'inline-flex whitespace-nowrap rounded-md border px-1.5 py-0.5 text-[10px] font-semibold',
                            paymentStatusColors[payKey] || paymentStatusColors.unpaid,
                          )}
                          title={paymentStatusLabels[payKey] || inv.payment_status}
                        >
                          {paymentStatusShortLabels[payKey] || inv.payment_status}
                        </span>
                      </td>
                      <td className="px-2.5 py-2 text-xs align-middle whitespace-normal min-w-[12rem]">
                        {renderInvoiceRefFeesCell(inv)}
                      </td>
                      <td
                        className={cn(invTd, 'max-w-[7rem] truncate text-gray-600 dark:text-gray-300')}
                        title={isAutoInvoiceTab ? inv.vessel_type_name ?? '' : inv.created_by_label ?? ''}
                      >
                        {isAutoInvoiceTab ? inv.vessel_type_name ?? '—' : inv.created_by_label ?? '—'}
                      </td>
                      <td className={cn(invTd, 'text-right align-top')}>
                        <div className="inline-flex min-w-[7.5rem] flex-col items-end gap-1">
                          {invoiceSubTab !== 'trash' && payKey !== 'paid' && getInvoiceGrossAmount(inv) > 0 ? (
                            <div className="inline-flex items-center justify-end gap-1">
                              {savingDiscountId != null && String(savingDiscountId) === String(inv.id) ? (
                                <Loader2 className="h-3 w-3 animate-spin text-blue-500" />
                              ) : null}
                              <span className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">
                                Giảm
                              </span>
                              <input
                                type="number"
                                min={0}
                                max={getInvoiceGrossAmount(inv)}
                                step={1000}
                                value={getDiscountDraft(inv)}
                                onChange={(e) => handleDiscountChange(inv, e.target.value)}
                                onBlur={() => {
                                  const key = String(inv.id);
                                  if (discountSaveTimers.current[key]) {
                                    clearTimeout(discountSaveTimers.current[key]);
                                    delete discountSaveTimers.current[key];
                                  }
                                  void persistDiscount(inv, getDiscountDraft(inv));
                                }}
                                disabled={
                                  isLoading ||
                                  (savingDiscountId != null &&
                                    String(savingDiscountId) === String(inv.id))
                                }
                                className={discountInputClass}
                                aria-label={`Giảm giá hóa đơn ${inv.invoice_number}`}
                              />
                            </div>
                          ) : getDiscountValue(inv) > 0 ? (
                            <span
                              className={cn(
                                'text-[10px] font-medium',
                                getInvoiceDiscountStatus(inv) === 'approved'
                                  ? 'text-emerald-600 dark:text-emerald-400'
                                  : 'text-amber-600 dark:text-amber-400',
                              )}
                            >
                              {getInvoiceDiscountStatus(inv) === 'approved' ? 'Đã duyệt' : 'Yêu cầu'}{' '}
                              {formatMoney(getDiscountValue(inv))} ₫
                            </span>
                          ) : null}
                          <span
                            className={cn(
                              dt.mono,
                              'font-semibold text-gray-900 dark:text-white text-right',
                            )}
                          >
                            {formatInvoiceTotalCell(inv, isAutoInvoiceTab)}
                          </span>
                        </div>
                      </td>
                      <td className="px-2.5 py-2 text-xs align-top min-w-[9rem]">
                        {invoiceSubTab !== 'trash' ? (
                          <div className="relative">
                            {savingNoteId != null && String(savingNoteId) === String(inv.id) ? (
                              <Loader2 className="absolute right-1 top-1 h-3 w-3 animate-spin text-blue-500" />
                            ) : null}
                            <textarea
                              rows={2}
                              value={getNoteDraft(inv)}
                              onChange={(e) => handleNoteChange(inv, e.target.value)}
                              onBlur={() => {
                                const key = String(inv.id);
                                if (noteSaveTimers.current[key]) {
                                  clearTimeout(noteSaveTimers.current[key]);
                                  delete noteSaveTimers.current[key];
                                }
                                void persistNotes(inv, getNoteDraft(inv));
                              }}
                              disabled={
                                isLoading ||
                                (savingNoteId != null && String(savingNoteId) === String(inv.id))
                              }
                              placeholder="Nhập ghi chú..."
                              className={noteInputClass}
                              aria-label={`Ghi chú hóa đơn ${inv.invoice_number}`}
                            />
                          </div>
                        ) : (
                          <span
                            className="block max-w-[14rem] truncate text-gray-500 dark:text-gray-400"
                            title={inv.notes ?? ''}
                          >
                            {inv.notes?.trim() ? inv.notes : '—'}
                          </span>
                        )}
                      </td>
                      <td className={cn(invTd, 'text-right')}>
                        <div className="inline-flex items-center justify-end gap-0.5">
                          {getInvoiceDetectionId(inv) != null ? (
                            <button
                              type="button"
                              onClick={() => openCompareModal(inv)}
                              className={cn(
                                'p-1.5 rounded-md transition-colors',
                                'text-indigo-600 hover:text-indigo-500 hover:bg-indigo-50 dark:text-indigo-400 dark:hover:bg-indigo-500/10',
                              )}
                              title="Đối chiếu"
                              aria-label="Đối chiếu"
                            >
                              <Eye className="w-3.5 h-3.5" />
                            </button>
                          ) : null}
                          {invoiceSubTab !== 'trash' && payKey !== 'paid' ? (
                            <button
                              type="button"
                              onClick={() => onOpenPayment(inv)}
                              className={cn(
                                'p-1.5 rounded-md transition-colors',
                                'text-blue-600 hover:text-blue-500 hover:bg-blue-50 dark:text-blue-400 dark:hover:bg-blue-500/10',
                              )}
                              title="Thanh toán"
                              aria-label="Thanh toán"
                            >
                              <Banknote className="w-3.5 h-3.5" />
                            </button>
                          ) : null}
                          {invoiceSubTab !== 'trash' ? (
                            <button
                              type="button"
                              onClick={() => onDeleteInvoice(inv.id)}
                              disabled={isLoading}
                              className={cn(
                                'p-1.5 rounded-md transition-colors',
                                'text-red-600 hover:text-red-500 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-500/10 disabled:opacity-50',
                              )}
                              title="Xóa"
                              aria-label="Xóa"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          ) : null}
                          {invoiceSubTab === 'trash' && getInvoiceDetectionId(inv) == null ? (
                            <span className="text-gray-400">—</span>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td
                    colSpan={invoiceTableColSpan}
                    className={cn(invTd, 'py-10 text-center text-sm text-gray-500 dark:text-gray-400')}
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

      <DetectionCompareModal
        open={compareOpen}
        onClose={() => setCompareOpen(false)}
        shipLabel={compareInvoice ? getInvoiceShipLabel(compareInvoice, vessels) : '—'}
        detectionId={compareInvoice ? getInvoiceDetectionId(compareInvoice) : null}
        contextLabel={
          compareInvoice ? `Hóa đơn: ${compareInvoice.invoice_number}` : undefined
        }
      />
    </div>
  );
};
