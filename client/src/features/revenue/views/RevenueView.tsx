import React, { useEffect, useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useRevenueStore } from '../store/revenueStore';
import { useVesselStore } from '../../vessels/store/vesselStore';
import { useOrderStore } from '../../orders/store/orderStore';
import type { FeeConfigRead } from '../../../types/api.types';
import { revenueApi, type InvoiceCreate, type PaymentCreate, type FeeConfigCreate } from '../services/revenueApi';
import { downloadBlobFile } from '../../../utils/download-blob';
import { ApiError } from '../../../services/httpClient';
import { isoInLocalDateRange, matchesAnyField } from '../../../utils/table-filters';
import {
  formatMoney,
  getInvoiceBerthMinutes,
  isInvoicePayable,
  sumInvoiceDisplayAmounts,
} from '../components/revenue-invoice-display';
import { BulkPaymentConfirmModal } from '../components/BulkPaymentConfirmModal';
import { BulkPaymentMethodChoiceModal } from '../components/BulkPaymentMethodChoiceModal';
import { BulkSepayPaymentModal } from '../components/BulkSepayPaymentModal';
import { normalizeFeeBillingUnit } from '../../../utils/fee-billing-unit';
import { useFilterOptions } from '../../../hooks/useFilterOptions';
import { invoiceSchema, paymentSchema, feeSchema, type FeeFormValues } from '../revenue-schemas';
import { feeConfigVesselTypeLabel } from '../utils/revenue-fee-helpers';
import { RevenueMainTabs, type RevenueMainTab } from '../components/RevenueMainTabs';
import { RevenueInvoiceSection } from '../components/RevenueInvoiceSection';
import { RevenueFeesSection } from '../components/RevenueFeesSection';
import { RevenueModals } from '../components/RevenueModals';
import { RevenueExcelExportChoiceModal } from '../components/RevenueExcelExportChoiceModal';
import { SepayPaymentModal } from '../components/SepayPaymentModal';
import {
  PaymentMethodChoiceModal,
  type PaymentMethodChoice,
} from '../components/PaymentMethodChoiceModal';
import type { InvoiceRead } from '../../../types/api.types';

export const RevenueView: React.FC = () => {
  const [activeTab, setActiveTab] = useState<RevenueMainTab>('invoices');
  const [isInvoiceModalOpen, setIsInvoiceModalOpen] = useState(false);
  const [isPaymentModalOpen, setIsPaymentModalOpen] = useState(false);
  const [isPaymentChoiceModalOpen, setIsPaymentChoiceModalOpen] = useState(false);
  const [isSepayPaymentModalOpen, setIsSepayPaymentModalOpen] = useState(false);
  const [pendingPaymentInvoice, setPendingPaymentInvoice] = useState<InvoiceRead | null>(null);
  const [paymentModalTitle, setPaymentModalTitle] = useState('Ghi Nhận Thanh Toán');
  const [lockPaymentMethod, setLockPaymentMethod] = useState<'cash' | undefined>(undefined);
  const [isFeeModalOpen, setIsFeeModalOpen] = useState(false);
  const [isBulkPaymentChoiceModalOpen, setIsBulkPaymentChoiceModalOpen] = useState(false);
  const [isBulkCashConfirmModalOpen, setIsBulkCashConfirmModalOpen] = useState(false);
  const [isBulkSepayModalOpen, setIsBulkSepayModalOpen] = useState(false);
  const [selectedInvoiceId, setSelectedInvoiceId] = useState<string | number | null>(null);
  const [editingFeeId, setEditingFeeId] = useState<string | number | null>(null);
  const [invQ, setInvQ] = useState('');
  const [invMinBerthMinutes, setInvMinBerthMinutes] = useState('');
  const [invShipIdFilter, setInvShipIdFilter] = useState('');
  const [invVesselTypeFilter, setInvVesselTypeFilter] = useState('');
  const [invDateFrom, setInvDateFrom] = useState('');
  const [invDateTo, setInvDateTo] = useState('');
  const [invMinTotal, setInvMinTotal] = useState('');
  const [invMaxTotal, setInvMaxTotal] = useState('');
  const [feeQ, setFeeQ] = useState('');
  const [feeTypeId, setFeeTypeId] = useState('');
  const [feeActive, setFeeActive] = useState<'all' | 'on' | 'off'>('all');
  const [feeDateFrom, setFeeDateFrom] = useState('');
  const [feeDateTo, setFeeDateTo] = useState('');
  const [isExporting, setIsExporting] = useState(false);
  const [isExcelExportChoiceModalOpen, setIsExcelExportChoiceModalOpen] = useState(false);
  const [allRevenueCount, setAllRevenueCount] = useState<number | null>(null);

  const {
    invoices,
    feeConfigs,
    invoiceSubTab,
    isLoading,
    setInvoiceSubTab,
    setInvoiceListKind,
    fetchInvoices,
    fetchFeeConfigs,
    createInvoice,
    recordPayment,
    recordBulkPayments,
    deleteInvoice,
    upsertFeeConfig,
    deleteFeeConfig,
  } = useRevenueStore();

  const { vesselTypes, fetchVesselTypes } = useVesselStore();
  const { vessels: filterVessels, vesselTypes: filterVesselTypes } = useFilterOptions();
  const { orders, fetchOrders } = useOrderStore();

  const invoiceForm = useForm<InvoiceCreate>({
    resolver: zodResolver(invoiceSchema),
    defaultValues: { items: [{ description: '', quantity: 1, unit_price: 0 }] },
  });

  const paymentForm = useForm<PaymentCreate>({
    resolver: zodResolver(paymentSchema),
  });

  const feeForm = useForm<FeeFormValues>({
    resolver: zodResolver(feeSchema),
    defaultValues: {
      is_active: true,
      fee_name: '',
      vessel_type_id: '',
      unit: 'per_month',
      base_fee: 0,
      berth_limit_count: undefined,
      berth_limit_unit: undefined,
    },
  });

  const feeUnit = feeForm.watch('unit');

  useEffect(() => {
    if (feeUnit === 'none') {
      feeForm.setValue('base_fee', 0);
    }
  }, [feeUnit, feeForm]);

  useEffect(() => {
    if (activeTab === 'invoices') {
      setInvoiceListKind('standard');
    } else if (activeTab === 'auto_invoices') {
      setInvoiceListKind('ai');
    }
  }, [activeTab, setInvoiceListKind]);

  useEffect(() => {
    if (activeTab === 'invoices' || activeTab === 'auto_invoices') {
      void fetchInvoices();
      if (activeTab === 'invoices') {
        void fetchOrders();
      }
    } else {
      void fetchFeeConfigs();
      void fetchVesselTypes();
    }
  }, [
    activeTab,
    invoiceSubTab,
    fetchInvoices,
    fetchFeeConfigs,
    fetchOrders,
    fetchVesselTypes,
  ]);

  const filteredInvoices = useMemo(() => {
    return invoices.filter((inv) => {
      if (
        !matchesAnyField(
          invQ,
          inv.invoice_number,
          String(inv.order_id ?? ''),
          String(inv.vessel_id ?? ''),
          String(inv.detection_id ?? ''),
          inv.payment_status,
          inv.created_by_label ?? '',
        )
      ) {
        return false;
      }
      if (invMinBerthMinutes.trim()) {
        const berthMinutes = getInvoiceBerthMinutes(inv);
        const min = Number(invMinBerthMinutes);
        if (berthMinutes === null || !Number.isFinite(min) || berthMinutes < min) {
          return false;
        }
      }
      const matchedVessel = filterVessels.find((vessel) => String(vessel.id) === String(inv.vessel_id ?? ''));
      if (invShipIdFilter && String(inv.vessel_id ?? matchedVessel?.id ?? '') !== invShipIdFilter) {
        return false;
      }
      if (
        invVesselTypeFilter &&
        String(matchedVessel?.vessel_type_id ?? '') !== invVesselTypeFilter
      ) {
        return false;
      }
      if (!isoInLocalDateRange(inv.created_at, invDateFrom, invDateTo)) {
        return false;
      }
      const total = Number(inv.total_amount ?? 0);
      if (invMinTotal.trim() && total < Number(invMinTotal)) {
        return false;
      }
      if (invMaxTotal.trim() && total > Number(invMaxTotal)) {
        return false;
      }
      return true;
    });
  }, [
    invoices,
    invQ,
    invMinBerthMinutes,
    invShipIdFilter,
    invVesselTypeFilter,
    invDateFrom,
    invDateTo,
    invMinTotal,
    invMaxTotal,
    filterVessels,
  ]);

  const filteredFeeConfigs = useMemo(() => {
    return feeConfigs.filter((fee) => {
      if (!matchesAnyField(feeQ, fee.fee_name, feeConfigVesselTypeLabel(fee, vesselTypes))) {
        return false;
      }
      if (feeTypeId && String(fee.vessel_type_id ?? '') !== feeTypeId) {
        return false;
      }
      if (feeActive === 'on' && !fee.is_active) {
        return false;
      }
      if (feeActive === 'off' && fee.is_active) {
        return false;
      }
      const t = fee.created_at ?? fee.updated_at ?? fee.effective_from;
      if (!isoInLocalDateRange(t ?? undefined, feeDateFrom, feeDateTo)) {
        return false;
      }
      return true;
    });
  }, [feeConfigs, feeQ, feeTypeId, feeActive, feeDateFrom, feeDateTo, vesselTypes]);

  const isAutoInvoiceTab = activeTab === 'auto_invoices';

  const payableFilteredInvoices = useMemo(
    () => filteredInvoices.filter((inv) => isInvoicePayable(inv)),
    [filteredInvoices],
  );

  const bulkPaymentTotal = useMemo(
    () => sumInvoiceDisplayAmounts(payableFilteredInvoices),
    [payableFilteredInvoices],
  );

  const invFilterCount =
    (invQ.trim() ? 1 : 0) +
    (invMinBerthMinutes.trim() ? 1 : 0) +
    (invShipIdFilter ? 1 : 0) +
    (invVesselTypeFilter ? 1 : 0) +
    (invDateFrom ? 1 : 0) +
    (invDateTo ? 1 : 0) +
    (invMinTotal.trim() ? 1 : 0) +
    (invMaxTotal.trim() ? 1 : 0);

  const feeFilterCount =
    (feeQ.trim() ? 1 : 0) +
    (feeTypeId ? 1 : 0) +
    (feeActive !== 'all' ? 1 : 0) +
    (feeDateFrom ? 1 : 0) +
    (feeDateTo ? 1 : 0);

  const resetInvFilters = () => {
    setInvQ('');
    setInvMinBerthMinutes('');
    setInvShipIdFilter('');
    setInvVesselTypeFilter('');
    setInvDateFrom('');
    setInvDateTo('');
    setInvMinTotal('');
    setInvMaxTotal('');
  };

  const resetFeeFilters = () => {
    setFeeQ('');
    setFeeTypeId('');
    setFeeActive('all');
    setFeeDateFrom('');
    setFeeDateTo('');
  };

  const onInvoiceSubmit = async (data: InvoiceCreate) => {
    try {
      await createInvoice(data);
      setIsInvoiceModalOpen(false);
      invoiceForm.reset();
    } catch (err) {
      console.error(err);
    }
  };

  const handleBulkPaymentConfirm = async () => {
    if (payableFilteredInvoices.length === 0) {
      return;
    }
    try {
      const result = await recordBulkPayments({
        invoice_ids: payableFilteredInvoices.map((inv) => Number(inv.id)),
        payment_method: 'cash',
        notes: invFilterCount > 0 ? 'Thanh toán hàng loạt (theo bộ lọc)' : 'Thanh toán hàng loạt',
      });
      setIsBulkCashConfirmModalOpen(false);
      window.alert(
        `Đã thanh toán ${result.invoice_count} hóa đơn — ${formatMoney(result.total_amount)} ₫`,
      );
    } catch (err) {
      console.error(err);
    }
  };

  const onPaymentSubmit = async (data: PaymentCreate) => {
    try {
      if (selectedInvoiceId) {
        await recordPayment(selectedInvoiceId, data);
        setIsPaymentModalOpen(false);
        paymentForm.reset();
        setSelectedInvoiceId(null);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleDeleteInvoice = async (invId: string | number) => {
    if (
      !window.confirm(
        'Xóa hóa đơn này? Hóa đơn sẽ chuyển vào tab «Đã xóa» (xóa mềm), không còn trong danh sách chờ / đã thanh toán.',
      )
    ) {
      return;
    }
    try {
      if (selectedInvoiceId != null && String(selectedInvoiceId) === String(invId)) {
        setIsPaymentModalOpen(false);
        setSelectedInvoiceId(null);
        paymentForm.reset();
      }
      await deleteInvoice(invId);
    } catch (err) {
      console.error(err);
    }
  };

  const onFeeSubmit = async (data: FeeFormValues) => {
    try {
      const hasBerthLimit =
        data.berth_limit_count != null &&
        Number.isFinite(data.berth_limit_count) &&
        data.berth_limit_count > 0 &&
        data.berth_limit_unit;

      const payload: FeeConfigCreate = {
        fee_name: data.fee_name,
        base_fee: data.unit === 'none' ? 0 : data.base_fee,
        unit: data.unit,
        is_active: data.is_active,
        vessel_type_id: data.vessel_type_id ? Number(data.vessel_type_id) : undefined,
        berth_limit_count: hasBerthLimit ? data.berth_limit_count : null,
        berth_limit_unit: hasBerthLimit ? data.berth_limit_unit : null,
      };
      await upsertFeeConfig(editingFeeId, payload);
      setIsFeeModalOpen(false);
      feeForm.reset();
      setEditingFeeId(null);
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : 'Lưu cấu hình phí thất bại. Thử lại sau.';
      window.alert(msg);
      console.error(err);
    }
  };

  const handleEditFee = (fee: FeeConfigRead) => {
    setEditingFeeId(fee.id);
    feeForm.reset({
      fee_name: fee.fee_name,
      vessel_type_id: fee.vessel_type_id != null ? String(fee.vessel_type_id) : '',
      unit: normalizeFeeBillingUnit(fee.unit),
      base_fee: Number(fee.base_fee),
      is_active: fee.is_active,
      berth_limit_count:
        fee.berth_limit_count != null && fee.berth_limit_count > 0
          ? fee.berth_limit_count
          : undefined,
      berth_limit_unit:
        fee.berth_limit_unit === 'day' || fee.berth_limit_unit === 'month'
          ? fee.berth_limit_unit
          : undefined,
    });
    setIsFeeModalOpen(true);
  };

  const handleDeleteFee = async (fee: FeeConfigRead) => {
    if (
      !window.confirm(
        'Xóa vĩnh viễn cấu hình phí này khỏi cơ sở dữ liệu? Hành động không hoàn tác. (Muốn chỉ tạm ngừng định giá, dùng checkbox «Đang áp dụng» khi chỉnh sửa.)',
      )
    ) {
      return;
    }
    try {
      if (editingFeeId != null && String(editingFeeId) === String(fee.id)) {
        setIsFeeModalOpen(false);
        setEditingFeeId(null);
        feeForm.reset({
          is_active: true,
          fee_name: '',
          vessel_type_id: '',
          unit: 'per_month',
          base_fee: 0,
          berth_limit_count: undefined,
          berth_limit_unit: undefined,
        });
      }
      await deleteFeeConfig(fee.id);
    } catch (err) {
      console.error(err);
    }
  };

  const openAddFeeModal = () => {
    setEditingFeeId(null);
    feeForm.reset({
      is_active: true,
      fee_name: '',
      vessel_type_id: '',
      unit: 'per_month',
      base_fee: 0,
      berth_limit_count: undefined,
      berth_limit_unit: undefined,
    });
    setIsFeeModalOpen(true);
  };

  const exportStamp = () => new Date().toISOString().slice(0, 10);

  const openExcelExportModal = () => {
    setIsExcelExportChoiceModalOpen(true);
    setAllRevenueCount(null);
    void revenueApi
      .getRevenueExportStats()
      .then((stats) => setAllRevenueCount(stats.total_invoices))
      .catch(() => {
        setAllRevenueCount(null);
      });
  };

  const handleExportInvoicesAll = async () => {
    setIsExporting(true);
    setIsExcelExportChoiceModalOpen(false);
    try {
      const blob = await revenueApi.exportAllInvoicesExcel();
      downloadBlobFile(blob, `revenue_all_history_${exportStamp()}.xlsx`);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Xuất Excel thất bại';
      window.alert(message);
      console.error(err);
    } finally {
      setIsExporting(false);
    }
  };

  const handleExportInvoicesFiltered = async () => {
    if (filteredInvoices.length === 0) {
      return;
    }
    setIsExporting(true);
    setIsExcelExportChoiceModalOpen(false);
    try {
      const blob = await revenueApi.exportInvoicesExcel({
        invoice_ids: filteredInvoices.map((inv) => Number(inv.id)),
        list_kind: activeTab === 'auto_invoices' ? 'ai' : 'invoices',
        invoice_sub_tab: invoiceSubTab,
      });
      downloadBlobFile(
        blob,
        `revenue_${activeTab === 'auto_invoices' ? 'ai' : 'invoices'}_filtered_${invoiceSubTab}_${exportStamp()}.xlsx`,
      );
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Xuất Excel thất bại';
      window.alert(message);
      console.error(err);
    } finally {
      setIsExporting(false);
    }
  };

  const handleExportFeeConfigs = async () => {
    if (filteredFeeConfigs.length === 0) {
      return;
    }
    setIsExporting(true);
    try {
      const blob = await revenueApi.exportFeeConfigsExcel(
        filteredFeeConfigs.map((fee) => Number(fee.id)),
      );
      downloadBlobFile(blob, `revenue_fee_configs_${exportStamp()}.xlsx`);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Xuất Excel thất bại';
      window.alert(message);
      console.error(err);
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <RevenueMainTabs activeTab={activeTab} onTabChange={setActiveTab} />

      {activeTab === 'invoices' || activeTab === 'auto_invoices' ? (
        <RevenueInvoiceSection
          isAutoInvoiceTab={isAutoInvoiceTab}
          invoiceSubTab={invoiceSubTab}
          onInvoiceSubTab={setInvoiceSubTab}
          filteredInvoices={filteredInvoices}
          invoices={invoices}
          isLoading={isLoading}
          invQ={invQ}
          setInvQ={setInvQ}
          invMinBerthMinutes={invMinBerthMinutes}
          setInvMinBerthMinutes={setInvMinBerthMinutes}
          invShipIdFilter={invShipIdFilter}
          setInvShipIdFilter={setInvShipIdFilter}
          invVesselTypeFilter={invVesselTypeFilter}
          setInvVesselTypeFilter={setInvVesselTypeFilter}
          invDateFrom={invDateFrom}
          setInvDateFrom={setInvDateFrom}
          invDateTo={invDateTo}
          setInvDateTo={setInvDateTo}
          invMinTotal={invMinTotal}
          setInvMinTotal={setInvMinTotal}
          invMaxTotal={invMaxTotal}
          setInvMaxTotal={setInvMaxTotal}
          resetInvFilters={resetInvFilters}
          invFilterCount={invFilterCount}
          vessels={filterVessels}
          vesselTypes={filterVesselTypes}
          onOpenCreateInvoice={() => setIsInvoiceModalOpen(true)}
          onOpenPayment={(inv) => {
            setPendingPaymentInvoice(inv);
            setIsPaymentChoiceModalOpen(true);
          }}
          onDeleteInvoice={handleDeleteInvoice}
          payableCount={payableFilteredInvoices.length}
          bulkPaymentTotal={bulkPaymentTotal}
          onOpenBulkPayment={() => setIsBulkPaymentChoiceModalOpen(true)}
          onExportExcel={openExcelExportModal}
          isExporting={isExporting}
        />
      ) : (
        <RevenueFeesSection
          feeQ={feeQ}
          setFeeQ={setFeeQ}
          feeTypeId={feeTypeId}
          setFeeTypeId={setFeeTypeId}
          feeActive={feeActive}
          setFeeActive={setFeeActive}
          feeDateFrom={feeDateFrom}
          setFeeDateFrom={setFeeDateFrom}
          feeDateTo={feeDateTo}
          setFeeDateTo={setFeeDateTo}
          resetFeeFilters={resetFeeFilters}
          feeFilterCount={feeFilterCount}
          vesselTypes={vesselTypes}
          filteredFeeConfigs={filteredFeeConfigs}
          feeConfigs={feeConfigs}
          isLoading={isLoading}
          onOpenAddFee={openAddFeeModal}
          onEditFee={handleEditFee}
          onDeleteFee={handleDeleteFee}
          onExportExcel={handleExportFeeConfigs}
          isExporting={isExporting}
        />
      )}

      <BulkPaymentMethodChoiceModal
        isOpen={isBulkPaymentChoiceModalOpen}
        onClose={() => setIsBulkPaymentChoiceModalOpen(false)}
        invoiceCount={payableFilteredInvoices.length}
        totalAmount={bulkPaymentTotal}
        hasActiveFilters={invFilterCount > 0}
        onSelect={(method: PaymentMethodChoice) => {
          setIsBulkPaymentChoiceModalOpen(false);
          if (method === 'transfer') {
            setIsBulkSepayModalOpen(true);
            return;
          }
          setIsBulkCashConfirmModalOpen(true);
        }}
      />

      <BulkPaymentConfirmModal
        isOpen={isBulkCashConfirmModalOpen}
        onClose={() => setIsBulkCashConfirmModalOpen(false)}
        invoiceCount={payableFilteredInvoices.length}
        totalAmount={bulkPaymentTotal}
        hasActiveFilters={invFilterCount > 0}
        isLoading={isLoading}
        onConfirm={() => void handleBulkPaymentConfirm()}
      />

      <BulkSepayPaymentModal
        isOpen={isBulkSepayModalOpen}
        onClose={() => setIsBulkSepayModalOpen(false)}
        invoices={payableFilteredInvoices}
        hasActiveFilters={invFilterCount > 0}
        onPaid={() => {
          void fetchInvoices();
        }}
      />

      <RevenueExcelExportChoiceModal
        isOpen={isExcelExportChoiceModalOpen}
        onClose={() => setIsExcelExportChoiceModalOpen(false)}
        onExportAll={() => void handleExportInvoicesAll()}
        onExportFiltered={() => void handleExportInvoicesFiltered()}
        totalCount={allRevenueCount ?? 0}
        filteredCount={filteredInvoices.length}
        tabCount={invoices.length}
        isExporting={isExporting}
      />

      <PaymentMethodChoiceModal
        isOpen={isPaymentChoiceModalOpen}
        onClose={() => {
          setIsPaymentChoiceModalOpen(false);
          setPendingPaymentInvoice(null);
        }}
        invoice={pendingPaymentInvoice}
        onSelect={(method: PaymentMethodChoice) => {
          if (!pendingPaymentInvoice) {
            return;
          }
          setIsPaymentChoiceModalOpen(false);
          if (method === 'transfer') {
            setIsSepayPaymentModalOpen(true);
            return;
          }
          setSelectedInvoiceId(pendingPaymentInvoice.id);
          setPaymentModalTitle('Thanh Toán Tiền Mặt');
          setLockPaymentMethod('cash');
          paymentForm.reset({
            amount: Number(pendingPaymentInvoice.total_amount),
            payment_method: 'cash',
          });
          setIsPaymentModalOpen(true);
        }}
      />

      <SepayPaymentModal
        isOpen={isSepayPaymentModalOpen}
        onClose={() => {
          setIsSepayPaymentModalOpen(false);
          setPendingPaymentInvoice(null);
        }}
        invoice={pendingPaymentInvoice}
        onPaid={() => {
          void fetchInvoices();
        }}
      />

      <RevenueModals
        isInvoiceModalOpen={isInvoiceModalOpen}
        onCloseInvoice={() => setIsInvoiceModalOpen(false)}
        invoiceForm={invoiceForm}
        onInvoiceSubmit={onInvoiceSubmit}
        orders={orders}
        isPaymentModalOpen={isPaymentModalOpen}
        onClosePayment={() => {
          setIsPaymentModalOpen(false);
          setLockPaymentMethod(undefined);
          setPaymentModalTitle('Ghi Nhận Thanh Toán');
          setPendingPaymentInvoice(null);
        }}
        paymentForm={paymentForm}
        onPaymentSubmit={onPaymentSubmit}
        paymentModalTitle={paymentModalTitle}
        lockPaymentMethod={lockPaymentMethod}
        isFeeModalOpen={isFeeModalOpen}
        onCloseFee={() => setIsFeeModalOpen(false)}
        feeForm={feeForm}
        onFeeSubmit={onFeeSubmit}
        editingFeeId={editingFeeId}
        vesselTypes={vesselTypes}
        feeUnit={feeUnit}
        isLoading={isLoading}
      />
    </div>
  );
};
