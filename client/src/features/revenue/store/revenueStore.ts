import { create } from 'zustand';
import type { InvoiceRead, FeeConfigRead } from '../../../types/api.types';
import { revenueApi } from '../services/revenueApi';
import type {
  BulkPaymentCreate,
  BulkPaymentRead,
  InvoiceCreate,
  InvoicePageRequest,
  PaymentCreate,
  FeeConfigCreate,
  FeeConfigUpdatePayload,
} from '../services/revenueApi';
import { ApiError } from '../../../services/httpClient';
import type { PaymentRead } from '../../../types/api.types';

export type InvoiceSubTab = 'pending' | 'paid' | 'trash';

export type InvoiceListKind = 'standard' | 'ai';

interface RevenueState {
  invoices: InvoiceRead[];
  feeConfigs: FeeConfigRead[];
  invoiceSubTab: InvoiceSubTab;
  /** Tab «Hóa đơn» vs «Hóa đơn tự động» — quyết định filter creation_source */
  invoiceListKind: InvoiceListKind;
  isLoading: boolean;
  error: string | null;
  setInvoiceListKind: (kind: InvoiceListKind) => void;
  setInvoiceSubTab: (tab: InvoiceSubTab) => void;
  /**
   * Nạp ĐÚNG một trang hoá đơn (8 bộ lọc + sub-tab + sắp xếp do server xử lý) và
   * lưu vào `invoices`. Là `fetcher` của `usePagedQuery` ở `RevenueView`: hook giữ
   * trang/bộ lọc/sắp xếp, store giữ dòng của trang đang xem để các thao tác tại chỗ
   * (ghi chú, giảm giá, thanh toán hàng loạt) vẫn cập nhật được dòng đó.
   */
  fetchInvoicesPage: (request: InvoicePageRequest) => Promise<{
    items: InvoiceRead[];
    total: number;
  }>;
  fetchFeeConfigs: (activeOnly?: boolean) => Promise<void>;
  createInvoice: (data: InvoiceCreate) => Promise<void>;
  recordPayment: (invoiceId: string | number, data: PaymentCreate) => Promise<void>;
  recordBulkPayments: (data: BulkPaymentCreate) => Promise<BulkPaymentRead>;
  deleteInvoice: (id: string | number) => Promise<void>;
  updateInvoiceDiscount: (id: string | number, discountAmount: number) => Promise<void>;
  updateInvoiceNotes: (id: string | number, notes: string) => Promise<void>;
  upsertFeeConfig: (id: string | number | null, data: FeeConfigCreate) => Promise<void>;
  deleteFeeConfig: (id: string | number) => Promise<void>;
}

async function recordBulkPaymentsSequential(
  state: RevenueState,
  data: BulkPaymentCreate,
): Promise<BulkPaymentRead> {
  const payments: PaymentRead[] = [];
  let total = 0;
  const method = data.payment_method ?? 'cash';

  for (const rawId of data.invoice_ids) {
    const inv = state.invoices.find((row) => String(row.id) === String(rawId));
    if (!inv) {
      continue;
    }
    const amount = Number(inv.total_amount ?? 0);
    if (!Number.isFinite(amount) || amount <= 0) {
      continue;
    }
    const payment = await revenueApi.createPayment(rawId, {
      amount,
      payment_method: method,
      notes: data.notes,
    });
    payments.push(payment);
    total += amount;
  }

  if (payments.length === 0) {
    throw new Error('No payable invoices in the request');
  }

  return {
    invoice_count: payments.length,
    total_amount: total,
    payments,
  };
}

export const useRevenueStore = create<RevenueState>((set, get) => ({
  invoices: [],
  feeConfigs: [],
  invoiceSubTab: 'pending',
  invoiceListKind: 'standard',
  isLoading: false,
  error: null,

  setInvoiceListKind: (invoiceListKind) => {
    set({ invoiceListKind });
  },

  setInvoiceSubTab: (invoiceSubTab) => {
    // Không tự nạp lại: đổi sub-tab làm `filters` của `usePagedQuery` đổi, hook tự
    // đưa về trang 1 rồi nạp lại (một nguồn sự thật duy nhất cho trang).
    set({ invoiceSubTab });
  },

  fetchInvoicesPage: async (request) => {
    set({ isLoading: true, error: null });
    try {
      const page = await revenueApi.getInvoicesPage(request);
      // Dòng của trang mới và cờ loading được ghi trong CÙNG một lần `set`: sau mỗi
      // lần đổi trang/bộ lọc/reload, `invoices` là đúng các dòng đang hiển thị,
      // không bao giờ là trang cũ trộn với metadata mới.
      set({ invoices: page.items, isLoading: false });
      return page;
    } catch (err: any) {
      set({
        invoices: [],
        error: err.message || 'Failed to fetch invoices',
        isLoading: false,
      });
      // Ném lại để `usePagedQuery` cũng xoá `items`/`total` và hiện lỗi của hook.
      throw err;
    }
  },

  fetchFeeConfigs: async (activeOnly) => {
    set({ isLoading: true, error: null });
    try {
      const feeConfigs = await revenueApi.getFeeConfigs(activeOnly);
      set({ feeConfigs, isLoading: false });
    } catch (err: any) {
      set({ error: err.message || 'Failed to fetch fee configs', isLoading: false });
    }
  },

  // Các mutation dưới đây KHÔNG tự nạp lại danh sách: trang/bộ lọc/sắp xếp nằm ở
  // `usePagedQuery` của `RevenueView`, nên view gọi `reload()` sau mỗi mutation để
  // nạp lại ĐÚNG trang đang xem (thay vì tải lại toàn bộ như trước).
  createInvoice: async (data) => {
    set({ isLoading: true, error: null });
    try {
      await revenueApi.createInvoice(data);
      set({ isLoading: false });
    } catch (err: any) {
      set({ error: err.message || 'Failed to create invoice', isLoading: false });
      throw err;
    }
  },

  recordPayment: async (invoiceId, data) => {
    set({ isLoading: true, error: null });
    try {
      await revenueApi.createPayment(invoiceId, data);
      set({ isLoading: false });
    } catch (err: any) {
      set({ error: err.message || 'Failed to record payment', isLoading: false });
      throw err;
    }
  },

  recordBulkPayments: async (data) => {
    set({ isLoading: true, error: null });
    try {
      let result: BulkPaymentRead;
      try {
        result = await revenueApi.createBulkPayments(data);
      } catch (err) {
        if (err instanceof ApiError && (err.status === 404 || err.status === 405)) {
          // Đường dự phòng chỉ có `state.invoices` = các dòng của TRANG đang xem,
          // nên chỉ thanh toán được những hoá đơn đang tải (đúng danh sách mà nút
          // «Thanh toán tất cả» đang đếm).
          result = await recordBulkPaymentsSequential(get(), data);
        } else {
          throw err;
        }
      }
      set({ isLoading: false });
      return result;
    } catch (err: any) {
      set({ error: err.message || 'Failed to record bulk payments', isLoading: false });
      throw err;
    }
  },

  deleteInvoice: async (id) => {
    set({ isLoading: true, error: null });
    try {
      await revenueApi.deleteInvoice(id);
      set({ isLoading: false });
    } catch (err: any) {
      set({ error: err.message || 'Failed to delete invoice', isLoading: false });
      throw err;
    }
  },

  updateInvoiceNotes: async (id, notes) => {
    set({ error: null });
    const prevInvoices = get().invoices;
    const normalized = notes.trim();
    set((state) => ({
      invoices: state.invoices.map((inv) =>
        String(inv.id) === String(id) ? { ...inv, notes: normalized || null } : inv,
      ),
    }));
    try {
      const updated = await revenueApi.updateInvoice(id, { notes: normalized });
      set((state) => ({
        invoices: state.invoices.map((inv) =>
          String(inv.id) === String(id) ? { ...inv, ...updated } : inv,
        ),
      }));
    } catch (err: any) {
      set({ invoices: prevInvoices, error: err.message || 'Failed to update invoice notes' });
      throw err;
    }
  },

  updateInvoiceDiscount: async (id, discountAmount) => {
    set({ error: null });
    const prevInvoices = get().invoices;
    try {
      const updated = await revenueApi.updateInvoice(id, {
        discount_requested_amount: discountAmount,
      });
      set((state) => ({
        invoices: state.invoices.map((inv) =>
          String(inv.id) === String(id) ? { ...inv, ...updated } : inv,
        ),
      }));
    } catch (err: any) {
      set({ invoices: prevInvoices, error: err.message || 'Failed to request invoice discount' });
      throw err;
    }
  },

  upsertFeeConfig: async (id, data) => {
    set({ isLoading: true, error: null });
    try {
      if (id != null && id !== '') {
        const patch: FeeConfigUpdatePayload = {
          fee_name: data.fee_name,
          vessel_type_id: data.vessel_type_id,
          vessel_id: data.vessel_id,
          base_fee: data.base_fee,
          is_active: data.is_active,
          unit: data.unit,
          effective_from: data.effective_from,
          effective_to: data.effective_to,
          berth_limit_count: data.berth_limit_count,
          berth_limit_unit: data.berth_limit_unit,
          over_limit_penalty_amount: data.over_limit_penalty_amount,
          outside_hours_penalty_amount: data.outside_hours_penalty_amount,
          outside_hours_penalty_per_hour: data.outside_hours_penalty_per_hour,
          max_berth_duration_minutes: data.max_berth_duration_minutes,
          over_duration_penalty_amount: data.over_duration_penalty_amount,
          operating_hours: data.operating_hours,
        };
        await revenueApi.updateFeeConfig(id, patch);
      } else {
        await revenueApi.createFeeConfig(data);
      }
      await get().fetchFeeConfigs();
    } catch (err: any) {
      set({ error: err.message || 'Failed to save fee config', isLoading: false });
      throw err;
    }
  },

  deleteFeeConfig: async (id) => {
    set({ isLoading: true, error: null });
    try {
      await revenueApi.deleteFeeConfig(id);
      await get().fetchFeeConfigs();
    } catch (err: any) {
      set({ error: err.message || 'Failed to delete fee config', isLoading: false });
      throw err;
    }
  },
}));
