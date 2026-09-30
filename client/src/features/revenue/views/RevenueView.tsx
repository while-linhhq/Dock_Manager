import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useRevenueStore } from '../store/revenueStore';
import { useVesselStore } from '../../vessels/store/vesselStore';
import { useOrderStore } from '../../orders/store/orderStore';
import type { FeeConfigRead } from '../../../types/api.types';
import { revenueApi, type InvoiceCreate, type InvoiceFilters, type InvoiceSort, type PaymentCreate, type FeeConfigCreate } from '../services/revenueApi';
import { downloadBlobFile } from '../../../utils/download-blob';
import { ApiError } from '../../../services/httpClient';
import { isoInLocalDateRange, matchesAnyField } from '../../../utils/table-filters';
import {
  formatMoney,
  isInvoicePayable,
  sumInvoiceDisplayAmounts,
} from '../components/revenue-invoice-display';
import { BulkPaymentConfirmModal } from '../components/BulkPaymentConfirmModal';
import { BulkPaymentMethodChoiceModal } from '../components/BulkPaymentMethodChoiceModal';
import { BulkSepayPaymentModal } from '../components/BulkSepayPaymentModal';
import { normalizeFeeBillingUnit } from '../../../utils/fee-billing-unit';
import { useFilterOptions } from '../../../hooks/useFilterOptions';
import { usePagedQuery } from '../../../hooks/usePagedQuery';
import {
  invoiceSchema,
  paymentSchema,
  feeSchemaByType,
  type MonthlyFeeFormInput,
  type MonthlyFeeFormValues,
} from '../revenue-schemas';
import { feeConfigVesselLabel, feeConfigVesselTypeLabel } from '../utils/revenue-fee-helpers';
import { RevenueMainTabs, type RevenueMainTab } from '../components/RevenueMainTabs';
import { RevenueInvoiceSection } from '../components/RevenueInvoiceSection';
import { RevenueFeesSection } from '../components/RevenueFeesSection';
import { RevenueModals } from '../components/RevenueModals';
import {
  emptyOperatingHours,
  operatingHoursFromApi,
  operatingHoursToApi,
} from '../types/fee-operating-hours';
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
  // Menu chia phạm vi phí hiển thị: tàu lẻ (gắn vessel_id) vs loại tàu tháng (gắn vessel_type_id).
  const [feeScope, setFeeScope] = useState<'spot' | 'monthly'>('spot');
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
    invoiceListKind,
    isLoading,
    setInvoiceSubTab,
    setInvoiceListKind,
    fetchInvoicesPage,
    fetchFeeConfigs,
    createInvoice,
    recordPayment,
    recordBulkPayments,
    deleteInvoice,
    updateInvoiceDiscount,
    updateInvoiceNotes,
    upsertFeeConfig,
    deleteFeeConfig,
  } = useRevenueStore();

  const { vessels, vesselTypes, fetchVessels, fetchVesselTypes } = useVesselStore();
  const { vessels: filterVessels, vesselTypes: filterVesselTypes } = useFilterOptions();
  const { orders, fetchOrders } = useOrderStore();

  const invoiceForm = useForm<InvoiceCreate>({
    resolver: zodResolver(invoiceSchema),
    defaultValues: { items: [{ description: '', quantity: 1, unit_price: 0 }] },
  });

  const paymentForm = useForm<PaymentCreate>({
    resolver: zodResolver(paymentSchema),
  });

  const feeForm = useForm<MonthlyFeeFormInput, unknown, MonthlyFeeFormValues>({
    resolver: zodResolver(feeSchemaByType),
    defaultValues: {
      is_active: true,
      fee_name: '',
      vessel_type_id: '',
      unit: 'per_month',
      base_fee: 0,
      berth_limit_count: undefined,
      berth_limit_unit: undefined,
      over_limit_penalty_amount: undefined,
      outside_hours_penalty_amount: undefined,
      outside_hours_penalty_per_hour: undefined,
      operating_hours: {},
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
      // Danh sách hoá đơn do `usePagedQuery` tự nạp (trang/bộ lọc/sắp xếp ở dưới).
      if (activeTab === 'invoices') {
        void fetchOrders();
      }
    } else {
      void fetchFeeConfigs();
      void fetchVesselTypes();
      void fetchVessels();
    }
  }, [activeTab, fetchFeeConfigs, fetchOrders, fetchVesselTypes, fetchVessels]);

  // Tám bộ lọc + sub-tab + tab nguồn tạo → tham số API. Server lọc/sắp xếp, client
  // không lọc lại (trước đây `filteredInvoices` lọc trên tối đa 200 bản ghi).
  const invFilters = useMemo<InvoiceFilters>(
    () => ({
      subTab: invoiceSubTab,
      listKind: invoiceListKind,
      q: invQ.trim() || undefined,
      minBerthMinutes: invMinBerthMinutes.trim() || undefined,
      vesselId: invShipIdFilter || undefined,
      vesselTypeId: invVesselTypeFilter || undefined,
      dateFrom: invDateFrom || undefined,
      dateTo: invDateTo || undefined,
      minTotal: invMinTotal.trim() || undefined,
      maxTotal: invMaxTotal.trim() || undefined,
    }),
    [
      invoiceSubTab,
      invoiceListKind,
      invQ,
      invMinBerthMinutes,
      invShipIdFilter,
      invVesselTypeFilter,
      invDateFrom,
      invDateTo,
      invMinTotal,
      invMaxTotal,
    ],
  );

  // `usePagedQuery` là nguồn sự thật duy nhất cho trang/bộ lọc/sắp xếp của danh sách
  // hoá đơn. `fetcher` là action của store nên store giữ ĐÚNG các dòng của trang đang
  // hiển thị (thao tác ghi chú/giảm giá tại chỗ vẫn cập nhật được dòng đó); `filters`
  // truyền vào chỉ là giá trị KHỞI TẠO.
  const {
    total: invoicesTotal,
    page: invoicesPage,
    pageSize: invoicesPageSize,
    isLoading: invoicesLoading,
    error: invoicesError,
    setPage: setInvoicesPage,
    setPageSize: setInvoicesPageSize,
    setFilters: setInvoiceFilters,
    setSort: setInvoiceSort,
    reload: reloadInvoices,
  } = usePagedQuery<InvoiceRead, InvoiceFilters, InvoiceSort>({
    fetcher: fetchInvoicesPage,
    filters: invFilters,
  });

  // Đẩy nội dung bộ lọc xuống hook. Object đã memo hoá nên hiệu ứng chỉ chạy khi bộ
  // lọc THỰC SỰ đổi; hook tự đưa `page` về 1 rồi debounce trước khi gọi API.
  // Bỏ qua lần chạy đầu vì hook đã KHỞI TẠO bằng chính `invFilters` (đẩy lại đúng
  // object đó chỉ làm hook tăng token nạp lại → thêm một request thừa lúc mở trang).
  const pushedInvFiltersRef = useRef(invFilters);
  useEffect(() => {
    if (pushedInvFiltersRef.current === invFilters) {
      return;
    }
    pushedInvFiltersRef.current = invFilters;
    setInvoiceFilters(invFilters);
  }, [invFilters, setInvoiceFilters]);

  const filteredFeeConfigs = useMemo(() => {
    return feeConfigs.filter((fee) => {
      // Chia phạm vi: tàu lẻ (gắn vessel_id) vs loại tàu tháng (gắn vessel_type_id, không có vessel_id).
      const isSpotFee = fee.vessel_id != null && fee.vessel_type_id == null;
      const isMonthlyFee = fee.vessel_id == null && fee.vessel_type_id != null;
      if (feeScope === 'spot' && !isSpotFee) {
        return false;
      }
      if (feeScope === 'monthly' && !isMonthlyFee) {
        return false;
      }
      // Tìm kiếm: spot theo mã tàu, monthly theo loại tàu.
      const searchLabel =
        feeScope === 'spot'
          ? feeConfigVesselLabel(fee, vessels)
          : feeConfigVesselTypeLabel(fee, vesselTypes);
      if (!matchesAnyField(feeQ, fee.fee_name, searchLabel)) {
        return false;
      }
      // Lọc theo loại tàu chỉ áp dụng cho monthly; spot không có vessel_type_id.
      if (feeScope === 'monthly' && feeTypeId && String(fee.vessel_type_id ?? '') !== feeTypeId) {
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
  }, [feeConfigs, feeQ, feeScope, feeTypeId, feeActive, feeDateFrom, feeDateTo, vessels, vesselTypes]);

  // Đếm phí mỗi phạm vi để hiển thị badge trên menu.
  const feeScopeCounts = useMemo(() => {
    let spot = 0;
    let monthly = 0;
    for (const fee of feeConfigs) {
      if (fee.vessel_id != null && fee.vessel_type_id == null) {
        spot += 1;
      } else if (fee.vessel_id == null && fee.vessel_type_id != null) {
        monthly += 1;
      }
    }
    return { spot, monthly };
  }, [feeConfigs]);

  const isAutoInvoiceTab = activeTab === 'auto_invoices';

  // «Thanh toán tất cả» chỉ tác động lên các hoá đơn chưa thanh toán CỦA TRANG đang
  // xem (server chỉ trả một trang) — đúng danh sách mà nút đang đếm.
  const payableInvoices = useMemo(
    () => invoices.filter((inv) => isInvoicePayable(inv)),
    [invoices],
  );

  const bulkPaymentTotal = useMemo(
    () => sumInvoiceDisplayAmounts(payableInvoices),
    [payableInvoices],
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
      // Nạp lại ĐÚNG trang/bộ lọc đang xem sau khi tạo hoá đơn.
      reloadInvoices();
    } catch (err) {
      console.error(err);
    }
  };

  const handleBulkPaymentConfirm = async () => {
    if (payableInvoices.length === 0) {
      return;
    }
    try {
      const result = await recordBulkPayments({
        invoice_ids: payableInvoices.map((inv) => Number(inv.id)),
        payment_method: 'cash',
        notes: invFilterCount > 0 ? 'Thanh toán hàng loạt (theo bộ lọc)' : 'Thanh toán hàng loạt',
      });
      setIsBulkCashConfirmModalOpen(false);
      window.alert(
        `Đã thanh toán ${result.invoice_count} hóa đơn — ${formatMoney(result.total_amount)} ₫`,
      );
      reloadInvoices();
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
        reloadInvoices();
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
      reloadInvoices();
    } catch (err) {
      console.error(err);
    }
  };

  const onFeeSubmit = async (data: MonthlyFeeFormValues) => {
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
        // Cấu hình phí Doanh Thu gắn theo loại tàu (áp cho tàu tháng cùng loại).
        vessel_type_id: data.vessel_type_id ? Number(data.vessel_type_id) : undefined,
        berth_limit_count: hasBerthLimit ? data.berth_limit_count : null,
        berth_limit_unit: hasBerthLimit ? data.berth_limit_unit : null,
        over_limit_penalty_amount:
          data.over_limit_penalty_amount != null && data.over_limit_penalty_amount > 0
            ? data.over_limit_penalty_amount
            : null,
        // Tàu tháng dùng duy nhất đơn giá ngoài giờ theo giờ; xóa mức cố định/lượt cũ khi lưu.
        outside_hours_penalty_amount: null,
        outside_hours_penalty_per_hour:
          data.outside_hours_penalty_per_hour != null &&
          data.outside_hours_penalty_per_hour > 0
            ? data.outside_hours_penalty_per_hour
            : null,
        max_berth_duration_minutes:
          data.max_berth_duration_minutes != null &&
          Number.isFinite(data.max_berth_duration_minutes) &&
          data.max_berth_duration_minutes > 0
            ? data.max_berth_duration_minutes
            : null,
        over_duration_penalty_amount:
          data.over_duration_penalty_amount != null && data.over_duration_penalty_amount > 0
            ? data.over_duration_penalty_amount
            : null,
        operating_hours: operatingHoursToApi(data.operating_hours ?? emptyOperatingHours()),
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
      over_limit_penalty_amount:
        fee.over_limit_penalty_amount != null && Number(fee.over_limit_penalty_amount) > 0
          ? Number(fee.over_limit_penalty_amount)
          : undefined,
      outside_hours_penalty_amount: undefined,
      // Tương thích cấu hình tàu tháng cũ: số tiền/lượt trở thành đơn giá/giờ khi mở sửa.
      outside_hours_penalty_per_hour:
        fee.outside_hours_penalty_per_hour != null &&
        Number(fee.outside_hours_penalty_per_hour) > 0
          ? Number(fee.outside_hours_penalty_per_hour)
          : fee.outside_hours_penalty_amount != null &&
              Number(fee.outside_hours_penalty_amount) > 0
            ? Number(fee.outside_hours_penalty_amount)
            : undefined,
      max_berth_duration_minutes:
        fee.max_berth_duration_minutes != null && fee.max_berth_duration_minutes > 0
          ? fee.max_berth_duration_minutes
          : undefined,
      over_duration_penalty_amount:
        fee.over_duration_penalty_amount != null && Number(fee.over_duration_penalty_amount) > 0
          ? Number(fee.over_duration_penalty_amount)
          : undefined,
      operating_hours: operatingHoursFromApi(fee.operating_hours),
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
          over_limit_penalty_amount: undefined,
          outside_hours_penalty_amount: undefined,
          outside_hours_penalty_per_hour: undefined,
          operating_hours: emptyOperatingHours(),
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
      over_limit_penalty_amount: undefined,
      outside_hours_penalty_amount: undefined,
      outside_hours_penalty_per_hour: undefined,
      operating_hours: emptyOperatingHours(),
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
    // Server chỉ trả một trang, nên «Xuất theo filter» xuất đúng các dòng đang tải
    // (trang hiện tại + bộ lọc/sub-tab hiện tại) — khớp phần đếm trên modal.
    if (invoices.length === 0) {
      return;
    }
    setIsExporting(true);
    setIsExcelExportChoiceModalOpen(false);
    try {
      const blob = await revenueApi.exportInvoicesExcel({
        invoice_ids: invoices.map((inv) => Number(inv.id)),
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
          invoices={invoices}
          total={invoicesTotal}
          page={invoicesPage}
          pageSize={invoicesPageSize}
          onPageChange={setInvoicesPage}
          onPageSizeChange={setInvoicesPageSize}
          onSortChange={setInvoiceSort}
          isLoading={invoicesLoading}
          error={invoicesError}
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
          onUpdateDiscount={updateInvoiceDiscount}
          onUpdateNotes={updateInvoiceNotes}
          payableCount={payableInvoices.length}
          bulkPaymentTotal={bulkPaymentTotal}
          onOpenBulkPayment={() => setIsBulkPaymentChoiceModalOpen(true)}
          onExportExcel={openExcelExportModal}
          isExporting={isExporting}
        />
      ) : (
        <RevenueFeesSection
          feeQ={feeQ}
          setFeeQ={setFeeQ}
          feeScope={feeScope}
          setFeeScope={setFeeScope}
          feeScopeCounts={feeScopeCounts}
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
        invoiceCount={payableInvoices.length}
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
        invoiceCount={payableInvoices.length}
        totalAmount={bulkPaymentTotal}
        hasActiveFilters={invFilterCount > 0}
        isLoading={isLoading}
        onConfirm={() => void handleBulkPaymentConfirm()}
      />

      <BulkSepayPaymentModal
        isOpen={isBulkSepayModalOpen}
        onClose={() => setIsBulkSepayModalOpen(false)}
        invoices={payableInvoices}
        hasActiveFilters={invFilterCount > 0}
        onPaid={() => {
          // Nạp lại đúng trang đang xem sau khi hoá đơn được thanh toán.
          reloadInvoices();
        }}
      />

      <RevenueExcelExportChoiceModal
        isOpen={isExcelExportChoiceModalOpen}
        onClose={() => setIsExcelExportChoiceModalOpen(false)}
        onExportAll={() => void handleExportInvoicesAll()}
        onExportFiltered={() => void handleExportInvoicesFiltered()}
        totalCount={allRevenueCount ?? 0}
        filteredCount={invoices.length}
        tabCount={invoicesTotal}
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
          // Nạp lại đúng trang đang xem sau khi hoá đơn được thanh toán.
          reloadInvoices();
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
        paymentInvoice={pendingPaymentInvoice}
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
