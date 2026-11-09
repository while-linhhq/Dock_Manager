import { httpClient } from '../../../services/httpClient';
import type { OrderRead } from '../../../types/api.types';

export type OrderCreate = {
  vessel_id: string;
  cargo_details?: string;
  total_amount: number;
  status?: string;
}

export type OrderUpdate = {
  vessel_id?: string;
  cargo_details?: string;
  total_amount?: number;
  status?: string;
}

/**
 * Tám bộ lọc của trang đơn hàng — gửi thẳng thành tham số query của `/orders/`.
 * Giá trị rỗng nghĩa là bỏ hẳn tham số (server không lọc gì).
 */
export type OrderFilters = {
  /** Từ khóa: id đơn, mã tàu / tên tàu, mô tả hàng hoá. */
  q?: string;
  /** Trạng thái đã chuẩn hoá (`pending` | `completed` | `cancelled`). */
  status?: string;
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
 * Khóa sắp xếp hợp lệ — khớp whitelist `SORT_COLUMNS` của API đơn hàng
 * (`order_code`, `vessel`, `created_at`, `status`, `total_amount`).
 */
export const ORDER_SORT_KEYS = [
  'order_code',
  'vessel',
  'created_at',
  'status',
  'total_amount',
] as const;

export type OrderSortKey = (typeof ORDER_SORT_KEYS)[number];

export type OrderSort = {
  key: OrderSortKey;
  order: 'asc' | 'desc';
};

export function isOrderSortKey(value: string): value is OrderSortKey {
  return ORDER_SORT_KEYS.some((key) => key === value);
}

/** Một trang đơn hàng — khớp tham số `fetcher` của `usePagedQuery`. */
export type OrderPageRequest = {
  skip: number;
  limit: number;
  filters: OrderFilters;
  sort?: OrderSort;
};

/**
 * Ngày địa phương `YYYY-MM-DD` → instant UTC để server so với `created_at` —
 * đúng khoảng ngày mà bộ lọc client-side trước đây áp dụng. `endOfDay` dành cho
 * mốc "đến ngày" (23:59:59.999 giờ địa phương).
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
 * Ô lọc tiền → số; rỗng hoặc không phải số thì bỏ hẳn tham số, giữ đúng hành vi
 * cũ (`total < NaN` luôn false nên bộ lọc không hợp lệ không lọc gì).
 */
function toFilterNumber(value: string | undefined): number | undefined {
  const trimmed = (value ?? '').trim();
  if (!trimmed) {
    return undefined;
  }
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : undefined;
}

export const ordersApi = {
  /**
   * Danh mục đơn hàng cho dropdown (trang hoá đơn). Trần phân trang của server
   * là 200 nên xin tường minh 200 — trước đây client xin 500 và bị kẹp còn 200.
   */
  getOrders: async (skip: number = 0, limit: number = 200, status?: string): Promise<OrderRead[]> => {
    const params = new URLSearchParams({ skip: skip.toString(), limit: limit.toString() });
    if (status) params.append('status', status);
    return httpClient.get<OrderRead[]>(`/orders/?${params.toString()}`);
  },
  /** Một trang đơn hàng: 8 bộ lọc + sắp xếp chạy ở SQL phía server. */
  getOrdersPage: async (
    request: OrderPageRequest,
  ): Promise<{ items: OrderRead[]; total: number }> => {
    const { skip, limit, filters, sort } = request;
    return httpClient.getPaged<OrderRead>('/orders/', {
      skip,
      limit,
      q: filters.q || undefined,
      status: filters.status || undefined,
      vessel_id: filters.vesselId || undefined,
      vessel_type_id: filters.vesselTypeId || undefined,
      created_from: localDateToUtcIso(filters.dateFrom, false),
      created_to: localDateToUtcIso(filters.dateTo, true),
      min_total: toFilterNumber(filters.minTotal),
      max_total: toFilterNumber(filters.maxTotal),
      sort: sort?.key,
      order: sort?.order,
    });
  },
  getOrder: async (id: string): Promise<OrderRead> => {
    return httpClient.get<OrderRead>(`/orders/${id}`);
  },
  createOrder: async (data: OrderCreate): Promise<OrderRead> => {
    return httpClient.post<OrderRead>('/orders/', data);
  },
  updateOrder: async (id: string, data: OrderUpdate): Promise<OrderRead> => {
    return httpClient.put<OrderRead>(`/orders/${id}`, data);
  },
  updateStatus: async (id: string, status: string): Promise<OrderRead> => {
    return httpClient.patch<OrderRead>(`/orders/${id}/status`, { status });
  },
  deleteOrder: async (id: string): Promise<void> => {
    return httpClient.delete(`/orders/${id}`);
  },
};
