import type {
  DashboardStats,
  DetectionAnalyticsAcceptance,
  DetectionAnalyticsBucket,
  DetectionAnalyticsHour,
  DetectionAnalyticsShip,
} from '../../../types/api.types';

/**
 * Nhãn tiếng Việt của donut "Trạng thái duyệt" — GIỮ NGUYÊN chuỗi đang hiển thị,
 * đúng thứ tự cũ (`buildAcceptanceSplit`) và đúng thứ tự khóa API trả về:
 * `accepted` → 'Đã xác nhận', `rejected` → 'Chưa xác nhận', `pending` → 'Chưa gán'.
 */
export const ACCEPTANCE_LABELS = ['Đã xác nhận', 'Chưa xác nhận', 'Chưa gán'] as const;

/**
 * Trục giờ của biểu đồ "24 giờ qua" (cửa sổ cuộn cố định, không theo kỳ).
 *
 * `by_hour[].hour` là instant **UTC**; nhãn trục của biểu đồ là giờ **địa phương**
 * (bản cũ `buildDetectionsByHourLast24h` dùng `t.getHours()`), nên phải đi qua
 * `new Date(hour)` — KHÔNG được cắt chuỗi ISO rồi coi như giờ địa phương, nếu không
 * người dùng UTC+7 sẽ thấy biểu đồ lệch 7 tiếng mà trông vẫn hợp lý.
 */
export function buildHourAxisFromAnalytics(
  points?: DetectionAnalyticsHour[] | null,
): {
  categories: string[];
  data: number[];
} {
  return {
    categories: (points ?? []).map((point) => {
      const at = new Date(point.hour);
      if (Number.isNaN(at.getTime())) {
        // Dữ liệu hỏng: hiện nguyên chuỗi để lộ lỗi thay vì bịa ra một nhãn giờ.
        return point.hour;
      }
      return `${String(at.getHours()).padStart(2, '0')}:${String(at.getMinutes()).padStart(2, '0')}`;
    }),
    data: (points ?? []).map((point) => Number(point.count)),
  };
}

export function buildTopShipsFromAnalytics(
  topShips?: DetectionAnalyticsShip[] | null,
): {
  labels: string[];
  counts: number[];
} {
  return {
    labels: (topShips ?? []).map((ship) => ship.label),
    counts: (topShips ?? []).map((ship) => Number(ship.count)),
  };
}

export function buildAcceptanceFromAnalytics(
  acceptance?: DetectionAnalyticsAcceptance | null,
): {
  labels: string[];
  series: number[];
} {
  return {
    labels: [...ACCEPTANCE_LABELS],
    series: [acceptance?.accepted ?? 0, acceptance?.rejected ?? 0, acceptance?.pending ?? 0],
  };
}

/** Nhãn bucket ('< 50%', '50–75%', '≥ 75%') do server trả — đi thẳng ra biểu đồ. */
export function buildConfidenceFromAnalytics(
  buckets?: DetectionAnalyticsBucket[] | null,
): {
  labels: string[];
  series: number[];
} {
  return {
    labels: (buckets ?? []).map((bucket) => bucket.bucket),
    series: (buckets ?? []).map((bucket) => Number(bucket.count)),
  };
}

export function formatStatsSummary(stats: DashboardStats | null): Array<{ k: string; v: string }> {
  if (!stats) {
    return [];
  }
  return [
    { k: 'Tàu (đăng ký)', v: String(stats.total_vessels) },
    { k: 'Nhận diện (hôm nay)', v: String(stats.total_detections_today) },
    { k: 'Đơn chờ (hiện tại)', v: String(stats.pending_orders) },
    { k: 'Đơn hoàn thành (hôm nay)', v: String(stats.completed_orders_today) },
    { k: 'Hóa đơn chưa thanh toán', v: String(stats.unpaid_invoices) },
    { k: 'Camera bật', v: String(stats.active_cameras) },
    {
      k: 'Doanh thu (placeholder HĐ hôm nay)',
      v: `${Number(stats.total_revenue_today || 0).toLocaleString('vi-VN')} ₫`,
    },
  ];
}
