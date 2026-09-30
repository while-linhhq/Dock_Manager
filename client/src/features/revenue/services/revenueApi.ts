import { httpClient } from '../../../services/httpClient';
import type { InvoiceRead, FeeConfigRead, PaymentRead } from '../../../types/api.types';
// Chỉ import KIỂU (bị xoá khi biên dịch) nên không tạo vòng lặp runtime với store.
import type { InvoiceListKind, InvoiceSubTab } from '../store/revenueStore';

export type InvoiceCreate = {
  order_id: string;
  items: Array<{
    description: string;
    quantity: number;
    unit_price: number;
  }>;
}

export type PaymentCreate = {
  amount: number;
  payment_method: string;
  reference_number?: string;
  notes?: string;
};

export type BulkPaymentCreate = {
  invoice_ids: number[];
  payment_method?: string;
  notes?: string;
};

export type BulkPaymentRead = {
  invoice_count: number;
  total_amount: number | string;
  payments: PaymentRead[];
};

export type BulkSepaySessionRead = {
  reference_code: string;
  invoice_count: number;
  total_amount: number | string;
  status: string;
  invoice_ids: number[];
};

export type FeeConfigCreate = {
  fee_name: string;
  vessel_type_id?: number | null;
  vessel_id?: number | null;
  base_fee: number;
  unit?: string | null;
  is_active?: boolean;
  effective_from?: string | null;
  effective_to?: string | null;
  berth_limit_count?: number | null;
  berth_limit_unit?: 'day' | 'month' | null;
  over_limit_penalty_amount?: number | null;
  outside_hours_penalty_amount?: number | null;
  outside_hours_penalty_per_hour?: number | null;
  max_berth_duration_minutes?: number | null;
  over_duration_penalty_amount?: number | null;
  operating_hours?: Record<string, unknown> | null;
}

export type FeeConfigUpdatePayload = {
  fee_name?: string;
  vessel_type_id?: number | null;
  vessel_id?: number | null;
  base_fee?: number;
  unit?: string | null;
  is_active?: boolean;
  effective_from?: string | null;
  effective_to?: string | null;
  berth_limit_count?: number | null;
  berth_limit_unit?: 'day' | 'month' | null;
  over_limit_penalty_amount?: number | null;
  outside_hours_penalty_amount?: number | null;
  outside_hours_penalty_per_hour?: number | null;
  max_berth_duration_minutes?: number | null;
  over_duration_penalty_amount?: number | null;
  operating_hours?: Record<string, unknown> | null;
}

export type SepayBankInfo = {
  bank_account: string;
  bank_name: string;
  account_name: string;
  sync_configured?: boolean;
};

export type InvoicePaymentStatus = {
  payment_status: string;
  paid_at?: string | null;
};

export type InvoiceUpdatePayload = {
  discount_requested_amount?: number;
  notes?: string;
};

/**
 * Tám bộ lọc của bảng hoá đơn (giữ nguyên tên state ở `RevenueView`) cộng với
 * chế độ đang xem — tất cả gửi thẳng thành tham số query của API.
 *
 * `created_from`/`created_to` là tên tham số của endpoint hoá đơn (không phải
 * `occurred_from`/`occurred_to` như bảng nhận diện).
 */
export type InvoiceFilters = {
  /** Sub-tab đang chọn — quyết định tập bản ghi server trả về. */
  subTab: InvoiceSubTab;
  /** Tab «Hóa đơn» vs «Hóa đơn tự động» — quyết định nguồn tạo. */
  listKind: InvoiceListKind;
  /** Từ khoá: số HĐ, order/vessel/detection id, mã tàu, nhãn người tạo. */
  q?: string;
  /** Số phút neo đậu tối thiểu, tính từ `(end_time - start_time)` của detection. */
  minBerthMinutes?: string;
  /** `vessels.id` (không phải `ship_id`). */
  vesselId?: string;
  vesselTypeId?: string;
  /** Ngày địa phương `YYYY-MM-DD` (ô lọc `input type="date"`). */
  dateFrom?: string;
  dateTo?: string;
  /** Tổng tiền tối thiểu / tối đa (₫). */
  minTotal?: string;
  maxTotal?: string;
};

/**
 * Khóa sắp xếp hợp lệ — khớp whitelist `SORT_COLUMNS` của API hoá đơn.
 * Khoá `time` của whitelist là thứ tự MẶC ĐỊNH (không có cột nào trên bảng), nên
 * không xuất hiện ở đây: chưa sắp xếp cột nào thì không gửi `sort`/`order`.
 */
export const INVOICE_SORT_KEYS = [
  'invoice_number',
  'ship_order',
  'created_at',
  'deleted_at',
  'payment_status',
  'total_amount',
] as const;

export type InvoiceSortKey = (typeof INVOICE_SORT_KEYS)[number];

export type InvoiceSort = {
  key: InvoiceSortKey;
  order: 'asc' | 'desc';
};

export function isInvoiceSortKey(value: string): value is InvoiceSortKey {
  return INVOICE_SORT_KEYS.some((key) => key === value);
}

/** Một trang hoá đơn — khớp tham số `fetcher` của `usePagedQuery`. */
export type InvoicePageRequest = {
  skip: number;
  limit: number;
  filters: InvoiceFilters;
  sort?: InvoiceSort;
};

/**
 * Ngày địa phương `YYYY-MM-DD` → instant UTC để server so với `created_at` —
 * đúng khoảng ngày mà bộ lọc client-side trước đây áp dụng (`dayStartMs`/
 * `dayEndMs`). `endOfDay` dành cho mốc "đến ngày" (23:59:59.999 giờ địa phương).
 */
function localDateToUtcIso(value: string | undefined, endOfDay: boolean): string | undefined {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec((value ?? '').trim());
  if (!match) {
    return undefined;
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = endOfDay
    ? new Date(year, month - 1, day, 23, 59, 59, 999)
    : new Date(year, month - 1, day);
  // `new Date(y, m, d)` tự cuộn ngày/tháng không hợp lệ (31/02 → 02/03) nên so lại.
  if (date.getMonth() !== month - 1 || date.getDate() !== day) {
    return undefined;
  }
  return date.toISOString();
}

/**
 * Ô lọc số → số hữu hạn; rỗng hoặc không phải số thì bỏ hẳn tham số.
 * Giữ đúng hành vi cũ: bộ lọc tiền không phải số bị bỏ qua
 * (`total < NaN` luôn false), riêng ô phút neo rỗng cũng không lọc gì.
 */
function toFiniteFilterNumber(value: string | undefined): number | undefined {
  const raw = (value ?? '').trim();
  if (!raw) {
    return undefined;
  }
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : undefined;
}

export const revenueApi = {
  /**
   * Một trang hoá đơn: 8 bộ lọc, sub-tab và sắp xếp chạy ở SQL phía server.
   * `total` là tổng số bản ghi khớp bộ lọc (đọc từ `X-Total-Count`), không phải
   * số dòng của trang.
   */
  getInvoicesPage: async (request: InvoicePageRequest): Promise<{ items: InvoiceRead[]; total: number }> => {
    const { skip, limit, filters, sort } = request;
    const { subTab, listKind } = filters;

    return httpClient.getPaged<InvoiceRead>('/invoices/', {
      skip,
      limit,
      // Sub-tab: đúng ba nhánh lọc cũ của store (đã xoá / đã thanh toán / chờ thanh toán).
      deleted_only: subTab === 'trash' ? true : undefined,
      payment_status: subTab === 'paid' ? 'PAID' : undefined,
      awaiting_payment: subTab === 'pending' ? true : undefined,
      // Tab «Hóa đơn tự động» chỉ lấy nguồn AI; tab thường loại trừ nguồn AI.
      creation_source: listKind === 'ai' ? 'AI' : undefined,
      exclude_creation_source: listKind === 'ai' ? undefined : 'AI',
      q: filters.q?.trim() || undefined,
      vessel_id: filters.vesselId || undefined,
      vessel_type_id: filters.vesselTypeId || undefined,
      created_from: localDateToUtcIso(filters.dateFrom, false),
      created_to: localDateToUtcIso(filters.dateTo, true),
      min_total: toFiniteFilterNumber(filters.minTotal),
      max_total: toFiniteFilterNumber(filters.maxTotal),
      min_berth_minutes: toFiniteFilterNumber(filters.minBerthMinutes),
      // Chỉ gửi khi có cột đang sắp xếp. Không gửi thì server dùng mặc định
      // `time`/`desc` (= `created_at`/`deleted_at` desc theo sub-tab, kèm
      // tiebreaker `id desc`) — đúng thứ tự bảng vẫn hiển thị từ trước tới nay.
      sort: sort?.key,
      order: sort?.order,
    });
  },
  getInvoice: async (id: string): Promise<InvoiceRead> => {
    return httpClient.get<InvoiceRead>(`/invoices/${id}`);
  },
  getSepayBankInfo: async (): Promise<SepayBankInfo> => {
    return httpClient.get<SepayBankInfo>('/sepay/bank-info');
  },
  getInvoicePaymentStatus: async (invoiceId: string | number): Promise<InvoicePaymentStatus> => {
    return httpClient.get<InvoicePaymentStatus>(`/invoices/${invoiceId}/payment-status`);
  },
  createInvoice: async (data: InvoiceCreate): Promise<InvoiceRead> => {
    return httpClient.post<InvoiceRead>('/invoices/', {
      order_id: Number(data.order_id),
      items: data.items.map((it) => ({
        description: it.description,
        quantity: it.quantity,
        unit_price: it.unit_price,
      })),
    });
  },
  updateInvoice: async (
    id: string | number,
    data: InvoiceUpdatePayload,
  ): Promise<InvoiceRead> => {
    return httpClient.put<InvoiceRead>(`/invoices/${id}`, data);
  },
  deleteInvoice: async (id: string | number): Promise<void> => {
    await httpClient.delete(`/invoices/${id}`);
  },
  getPayments: async (invoiceId: string): Promise<PaymentRead[]> => {
    return httpClient.get<PaymentRead[]>(`/invoices/${invoiceId}/payments`);
  },
  createPayment: async (invoiceId: string | number, data: PaymentCreate): Promise<PaymentRead> => {
    return httpClient.post<PaymentRead>(`/invoices/${invoiceId}/payments`, {
      invoice_id: Number(invoiceId),
      amount: data.amount,
      payment_method: data.payment_method,
      payment_reference: data.reference_number,
      notes: data.notes,
    });
  },
  createBulkPayments: async (data: BulkPaymentCreate): Promise<BulkPaymentRead> => {
    return httpClient.post<BulkPaymentRead>('/invoices/bulk-payments', {
      invoice_ids: data.invoice_ids,
      payment_method: data.payment_method ?? 'cash',
      notes: data.notes,
    });
  },
  createBulkSepaySession: async (invoiceIds: number[]): Promise<BulkSepaySessionRead> => {
    return httpClient.post<BulkSepaySessionRead>('/invoices/bulk-sepay-session', {
      invoice_ids: invoiceIds,
    });
  },
  getBulkSepaySessionStatus: async (referenceCode: string): Promise<BulkSepaySessionRead> => {
    const ref = encodeURIComponent(referenceCode.trim().toUpperCase());
    return httpClient.get<BulkSepaySessionRead>(`/invoices/bulk-sepay-session/${ref}`);
  },
  getFeeConfigs: async (activeOnly: boolean = false): Promise<FeeConfigRead[]> => {
    return httpClient.get<FeeConfigRead[]>(`/fee-configs/?active_only=${activeOnly}`);
  },
  getFeeConfigsByVessel: async (
    vesselId: number,
    activeOnly: boolean = false,
  ): Promise<FeeConfigRead[]> => {
    return httpClient.get<FeeConfigRead[]>(
      `/fee-configs/?vessel_id=${vesselId}&active_only=${activeOnly}`,
    );
  },
  createFeeConfig: async (data: FeeConfigCreate): Promise<FeeConfigRead> => {
    return httpClient.post<FeeConfigRead>('/fee-configs/', data);
  },
  updateFeeConfig: async (
    id: string | number,
    data: FeeConfigUpdatePayload
  ): Promise<FeeConfigRead> => {
    return httpClient.put<FeeConfigRead>(`/fee-configs/${id}`, data);
  },
  deleteFeeConfig: async (id: string | number): Promise<void> => {
    await httpClient.delete(`/fee-configs/${id}`);
  },
  getRevenueExportStats: async (): Promise<{ total_invoices: number }> => {
    return httpClient.get<{ total_invoices: number }>('/exports/revenue-invoices/stats');
  },
  exportAllInvoicesExcel: async (): Promise<Blob> => {
    return httpClient.downloadBlob('/exports/revenue-invoices/all', {
      method: 'POST',
      body: JSON.stringify({}),
    });
  },
  exportInvoicesExcel: async (payload: {
    invoice_ids: number[];
    list_kind?: string;
    invoice_sub_tab?: string;
  }): Promise<Blob> => {
    return httpClient.downloadBlob('/exports/revenue-invoices', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },
  exportFeeConfigsExcel: async (feeConfigIds: number[]): Promise<Blob> => {
    return httpClient.downloadBlob('/exports/revenue-fee-configs', {
      method: 'POST',
      body: JSON.stringify({ fee_config_ids: feeConfigIds }),
    });
  },
};
