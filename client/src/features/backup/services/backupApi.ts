import { httpClient } from '../../../services/httpClient';
import type { AuditLogRead } from '../../../types/api.types';

export type DetectionMediaRead = {
  id: string;
  detection_id: string;
  media_type: 'image' | 'video';
  file_path: string;
  created_at: string;
}

/**
 * Năm bộ lọc của trang lịch sử — gửi thẳng thành tham số query của
 * `/audit-logs/`. `userId` giữ lại tham số cũ của API (UI chưa có ô chọn người
 * dùng nên hiện luôn bỏ trống).
 */
export type AuditLogFilters = {
  userId?: string;
  /** Từ khóa: `action`, `record_id`, tên / email người dùng. */
  q?: string;
  /** Lọc chứa trên `action`. */
  action?: string;
  /** Lọc chứa trên `table_name` (`entity_type` của payload). */
  tableName?: string;
  /** Ngày địa phương `YYYY-MM-DD` (ô lọc `input type="date"`). */
  dateFrom?: string;
  dateTo?: string;
};

/** Một trang audit-log — khớp tham số `fetcher` của `usePagedQuery`. */
export type AuditLogPageRequest = {
  skip: number;
  limit: number;
  filters: AuditLogFilters;
};

/**
 * Ngày địa phương `YYYY-MM-DD` → instant UTC để server so với `created_at` —
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

export const backupApi = {
  /**
   * Một trang lịch sử hệ thống. Không gửi `sort`/`order`: mặc định của endpoint
   * là `created_at desc` — đúng thứ tự mới-nhất-trước mà trang vẫn hiển thị
   * (`audit_log_repo.get_by_user` đã `order_by(created_at.desc())` từ trước).
   */
  getAuditLogsPage: async (
    request: AuditLogPageRequest,
  ): Promise<{ items: AuditLogRead[]; total: number }> => {
    const { skip, limit, filters } = request;
    return httpClient.getPaged<AuditLogRead>('/audit-logs/', {
      skip,
      limit,
      user_id: filters.userId || undefined,
      q: filters.q || undefined,
      action: filters.action || undefined,
      table_name: filters.tableName || undefined,
      created_from: localDateToUtcIso(filters.dateFrom, false),
      created_to: localDateToUtcIso(filters.dateTo, true),
    });
  },
  getDetectionMedia: async (detectionId: string): Promise<DetectionMediaRead[]> => {
    return httpClient.get<DetectionMediaRead[]>(`/detections/${detectionId}/media`);
  },
};
