import type { DashboardStats, DetectionRead } from '../../../types/api.types';
import { getDetectionShipLabel } from '../../../utils/detection-display';

/** 24 khung giờ kết thúc tại giờ hiện tại (local), đếm detection theo start_time/created_at. */
export function buildDetectionsByHourLast24h(detections: DetectionRead[]): {
  categories: string[];
  data: number[];
} {
  const now = Date.now();
  const slotMs = 60 * 60 * 1000;
  const slotStart = new Date(now);
  slotStart.setMinutes(0, 0, 0);
  slotStart.setMilliseconds(0);
  const start = slotStart.getTime() - 23 * slotMs;

  const categories: string[] = [];
  const data = new Array(24).fill(0);
  for (let i = 0; i < 24; i++) {
    const t = new Date(start + i * slotMs);
    categories.push(
      `${String(t.getHours()).padStart(2, '0')}:${String(t.getMinutes()).padStart(2, '0')}`,
    );
  }

  for (const d of detections) {
    const raw = d.start_time ?? d.created_at;
    if (!raw) {
      continue;
    }
    const ts = new Date(raw).getTime();
    if (Number.isNaN(ts) || ts < start || ts > now + slotMs) {
      continue;
    }
    const idx = Math.floor((ts - start) / slotMs);
    if (idx >= 0 && idx < 24) {
      data[idx] += 1;
    }
  }

  return { categories, data };
}

export function buildTopShipCounts(
  detections: DetectionRead[],
  topN = 8,
): { labels: string[]; counts: number[] } {
  const m = new Map<string, number>();
  for (const d of detections) {
    const k = getDetectionShipLabel(d);
    m.set(k, (m.get(k) ?? 0) + 1);
  }
  const sorted = [...m.entries()].sort((a, b) => b[1] - a[1]).slice(0, topN);
  return {
    labels: sorted.map(([k]) => k),
    counts: sorted.map(([, v]) => v),
  };
}

export function buildAcceptanceSplit(detections: DetectionRead[]): {
  labels: string[];
  series: number[];
} {
  let yes = 0;
  let no = 0;
  let unk = 0;
  for (const d of detections) {
    if (d.is_accepted === true) {
      yes += 1;
    } else if (d.is_accepted === false) {
      no += 1;
    } else {
      unk += 1;
    }
  }
  return {
    labels: ['Đã xác nhận', 'Chưa xác nhận', 'Chưa gán'],
    series: [yes, no, unk],
  };
}

export function buildConfidenceBuckets(detections: DetectionRead[]): {
  labels: string[];
  series: number[];
} {
  const b = [0, 0, 0];
  for (const d of detections) {
    const c = d.confidence;
    if (c == null || Number.isNaN(Number(c))) {
      continue;
    }
    const n = Number(c);
    if (n < 0.5) {
      b[0] += 1;
    } else if (n < 0.75) {
      b[1] += 1;
    } else {
      b[2] += 1;
    }
  }
  return {
    labels: ['< 50%', '50–75%', '≥ 75%'],
    series: b,
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
