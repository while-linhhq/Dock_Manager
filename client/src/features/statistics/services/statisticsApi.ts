import { httpClient } from '../../../services/httpClient';
import type { PortLogRead } from '../../../types/api.types';

export type OutsideHoursSummaryRow = {
  ship_id: string;
  /** Ngày VN dạng 'YYYY-MM-DD' */
  date: string;
  /** Số lượt neo ngoài khung giờ cho phép trong ngày đó */
  count: number;
};

/**
 * Sáu bộ lọc của trang thống kê — tất cả đều có tham số phía server nên không
 * còn bộ lọc nào chạy ở client:
 * - `shipId` → `ship_id` (khớp ĐÚNG mã tàu; trước đây client lọc `includes` nên
 *   "SG-7044" khớp lẫn cả "SG-70442"),
 * - `q` → `q` (server chỉ khớp chứa trên `track_id`, đúng ô "Track ID"),
 * - `vesselTypeId` → `vessel_type_id` (tra loại tàu qua `vessels.ship_id`),
 * - `minConfidence` → `min_confidence` (0–1),
 * - `dateFrom`/`dateTo` → `logged_from`/`logged_to` (instant UTC).
 */
export type PortLogFilters = {
  /** Mã tàu đầy đủ, lấy từ dropdown (không phải `vessels.id`). */
  shipId?: string;
  /** Từ khóa track_id. */
  q?: string;
  vesselTypeId?: string;
  /** Độ tin cậy tối thiểu, thang 0–1. */
  minConfidence?: string;
  /** Ngày địa phương `YYYY-MM-DD` (ô lọc `input type="date"`). */
  dateFrom?: string;
  dateTo?: string;
};

/** Khóa sắp xếp hợp lệ — khớp whitelist `SORT_COLUMNS` của API port-log. */
export const PORT_LOG_SORT_KEYS = ['time', 'voted_ship_id'] as const;

export type PortLogSortKey = (typeof PORT_LOG_SORT_KEYS)[number];

export type PortLogSort = {
  key: PortLogSortKey;
  order: 'asc' | 'desc';
};

export function isPortLogSortKey(value: string): value is PortLogSortKey {
  return PORT_LOG_SORT_KEYS.some((key) => key === value);
}

/** Một trang port-log — khớp tham số `fetcher` của `usePagedQuery`. */
export type PortLogPageRequest = {
  skip: number;
  limit: number;
  filters: PortLogFilters;
  sort?: PortLogSort;
};

/**
 * Ngày địa phương `YYYY-MM-DD` → instant UTC để server so với `logged_at` —
 * đúng khoảng ngày mà bộ lọc `isoInLocalDateRange` của client áp dụng trước đây.
 * `endOfDay` dành cho mốc "đến ngày" (23:59:59.999 giờ địa phương).
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

/** Ô lọc số → số hữu hạn; rỗng/không phải số thì bỏ hẳn tham số. */
function toFilterNumber(value: string | undefined): number | undefined {
  const trimmed = (value ?? '').trim();
  if (!trimmed) {
    return undefined;
  }
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : undefined;
}

export const statisticsApi = {
  /** Một trang nhật ký cảng: 6 bộ lọc + sắp xếp chạy ở SQL phía server. */
  getPortLogsPage: async (
    request: PortLogPageRequest,
  ): Promise<{ items: PortLogRead[]; total: number }> => {
    const { skip, limit, filters, sort } = request;
    return httpClient.getPaged<PortLogRead>('/port-logs/', {
      skip,
      limit,
      ship_id: filters.shipId || undefined,
      q: filters.q || undefined,
      vessel_type_id: filters.vesselTypeId || undefined,
      min_confidence: toFilterNumber(filters.minConfidence),
      logged_from: localDateToUtcIso(filters.dateFrom, false),
      logged_to: localDateToUtcIso(filters.dateTo, true),
      sort: sort?.key,
      order: sort?.order,
    });
  },
  getOutsideHoursSummary: async (
    dateFrom?: string,
    dateTo?: string,
    shipId?: string,
  ): Promise<OutsideHoursSummaryRow[]> => {
    const params = new URLSearchParams();
    if (dateFrom) params.append('date_from', dateFrom);
    if (dateTo) params.append('date_to', dateTo);
    if (shipId) params.append('ship_id', shipId);
    const qs = params.toString();
    return httpClient.get<OutsideHoursSummaryRow[]>(
      `/port-logs/outside-hours-summary${qs ? `?${qs}` : ''}`,
    );
  },
  exportExcel: async (logDate?: string, shipId?: string): Promise<Blob> => {
    const params = new URLSearchParams();
    if (logDate) params.append('log_date', logDate);
    if (shipId) params.append('ship_id', shipId);
    
    const response = await fetch(`${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'}/exports/port-logs?${params.toString()}`, {
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('auth_token')}`
      }
    });
    return response.blob();
  }
};
