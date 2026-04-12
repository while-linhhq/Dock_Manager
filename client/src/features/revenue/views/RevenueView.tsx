import React, { useEffect, useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useRevenueStore } from '../store/revenueStore';
import { useVesselStore } from '../../vessels/store/vesselStore';
import { useOrderStore } from '../../orders/store/orderStore';
import type { FeeConfigRead } from '../../../types/api.types';
import type { InvoiceCreate, PaymentCreate, FeeConfigCreate } from '../services/revenueApi';
import { isoInLocalDateRange, matchesAnyField } from '../../../utils/table-filters';
import { normalizeFeeBillingUnit } from '../../../utils/fee-billing-unit';
import { invoiceSchema, paymentSchema, feeSchema, type FeeFormValues } from '../revenue-schemas';
import { feeConfigVesselTypeLabel } from '../utils/revenue-fee-helpers';
import { RevenueMainTabs, type RevenueMainTab } from '../components/RevenueMainTabs';
import { RevenueInvoiceSection } from '../components/RevenueInvoiceSection';
import { RevenueFeesSection } from '../components/RevenueFeesSection';
import { RevenueModals } from '../components/RevenueModals';

export const RevenueView: React.FC = () => {
  const [activeTab, setActiveTab] = useState<RevenueMainTab>('invoices');
  const [isInvoiceModalOpen, setIsInvoiceModalOpen] = useState(false);
  const [isPaymentModalOpen, setIsPaymentModalOpen] = useState(false);
  const [isFeeModalOpen, setIsFeeModalOpen] = useState(false);
  const [selectedInvoiceId, setSelectedInvoiceId] = useState<string | number | null>(null);
  const [editingFeeId, setEditingFeeId] = useState<string | number | null>(null);
  const [invQ, setInvQ] = useState('');
  const [invPayStatus, setInvPayStatus] = useState('');
  const [invDateFrom, setInvDateFrom] = useState('');
  const [invDateTo, setInvDateTo] = useState('');
  const [invMinTotal, setInvMinTotal] = useState('');
  const [invMaxTotal, setInvMaxTotal] = useState('');
  const [feeQ, setFeeQ] = useState('');
  const [feeTypeId, setFeeTypeId] = useState('');
  const [feeActive, setFeeActive] = useState<'all' | 'on' | 'off'>('all');
  const [feeDateFrom, setFeeDateFrom] = useState('');
  const [feeDateTo, setFeeDateTo] = useState('');

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
    deleteInvoice,
    upsertFeeConfig,
    deleteFeeConfig,
  } = useRevenueStore();

  const { vesselTypes, fetchVesselTypes } = useVesselStore();
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
      if (
        invPayStatus &&
        String(inv.payment_status ?? '').toUpperCase() !== invPayStatus.toUpperCase()
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
  }, [invoices, invQ, invPayStatus, invDateFrom, invDateTo, invMinTotal, invMaxTotal]);

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

  const invFilterCount =
    (invQ.trim() ? 1 : 0) +
    (invPayStatus ? 1 : 0) +
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
    setInvPayStatus('');
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
      const payload: FeeConfigCreate = {
        fee_name: data.fee_name,
        base_fee: data.unit === 'none' ? 0 : data.base_fee,
        unit: data.unit,
        is_active: data.is_active,
        vessel_type_id: data.vessel_type_id ? Number(data.vessel_type_id) : undefined,
      };
      await upsertFeeConfig(editingFeeId, payload);
      setIsFeeModalOpen(false);
      feeForm.reset();
      setEditingFeeId(null);
    } catch (err) {
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
    });
    setIsFeeModalOpen(true);
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
          invPayStatus={invPayStatus}
          setInvPayStatus={setInvPayStatus}
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
          onOpenCreateInvoice={() => setIsInvoiceModalOpen(true)}
          onOpenPayment={(inv) => {
            setSelectedInvoiceId(inv.id);
            paymentForm.reset({ amount: Number(inv.total_amount) });
            setIsPaymentModalOpen(true);
          }}
          onDeleteInvoice={handleDeleteInvoice}
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
        />
      )}

      <RevenueModals
        isInvoiceModalOpen={isInvoiceModalOpen}
        onCloseInvoice={() => setIsInvoiceModalOpen(false)}
        invoiceForm={invoiceForm}
        onInvoiceSubmit={onInvoiceSubmit}
        orders={orders}
        isPaymentModalOpen={isPaymentModalOpen}
        onClosePayment={() => setIsPaymentModalOpen(false)}
        paymentForm={paymentForm}
        onPaymentSubmit={onPaymentSubmit}
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
