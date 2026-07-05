import type { DetectionRead } from '../types/api.types';
import { formatTimeVN, parseApiDate } from './date-time';

const UNKNOWN_SHIP_LABEL = 'KH\u00d4NG X\u00c1C \u0110\u1ecaNH';

export function getDetectionShipLabel(det: DetectionRead): string {
  const fromVessel = det.vessel?.ship_id?.trim();
  if (fromVessel) {
    return fromVessel;
  }
  const items = det.ocr_results;
  if (Array.isArray(items) && items.length > 0) {
    const first = items[0] as Record<string, unknown>;
    const id = first?.id;
    if (typeof id === 'string' && id.trim()) {
      return id.trim();
    }
  }
  return UNKNOWN_SHIP_LABEL;
}

export function getDetectionDisplayTimeIso(det: DetectionRead): string | null {
  const raw = det.start_time ?? det.created_at;
  if (!raw) {
    return null;
  }
  const d = parseApiDate(raw);
  return d ? raw : null;
}

/**
 * Mốc thời gian dùng để sắp xếp/hiển thị: ưu tiên berth_in_time (tàu IN vùng
 * neo đậu), fallback start_time rồi created_at. Trả về epoch ms để sort ổn định.
 */
export function getDetectionSortTs(det: DetectionRead): number {
  const raw = det.berth_in_time ?? det.start_time ?? det.created_at;
  const d = parseApiDate(raw);
  return d ? d.getTime() : 0;
}

/**
 * Thời lượng neo đậu = berth_out_time - berth_in_time. Nếu chưa OUT, dùng
 * end_time làm mốc kết thúc. Trả về chuỗi "Xh Ym" / "Ym Zs" hoặc '—'.
 */
export function formatBerthDuration(det: DetectionRead): string {
  const inRaw = det.berth_in_time;
  if (!inRaw) {
    return '—';
  }
  const start = parseApiDate(inRaw);
  const end = parseApiDate(det.berth_out_time ?? det.end_time);
  if (!start || !end) {
    return '—';
  }
  const seconds = Math.floor((end.getTime() - start.getTime()) / 1000);
  if (seconds < 0) {
    return '—';
  }
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) {
    return `${h}h ${m}m`;
  }
  if (m > 0) {
    return `${m}m ${s}s`;
  }
  return `${s}s`;
}

/**
 * Khoảng thời gian tính thời lượng neo đậu, dạng "HH:mm:ss → HH:mm:ss".
 * Ưu tiên cặp berth_in→berth_out (nhãn "neo đậu"); nếu thiếu berth, dùng cặp
 * start→end (nhãn "xuất hiện"). Trả về null nếu không đủ hai mốc.
 */
export function getBerthDurationRange(
  det: DetectionRead,
): { from: string; to: string; source: 'neo đậu' | 'xuất hiện' } | null {
  const inRaw = det.berth_in_time;
  const outRaw = det.berth_out_time ?? det.end_time;
  if (inRaw && outRaw) {
    const from = parseApiDate(inRaw);
    const to = parseApiDate(outRaw);
    if (from && to && to.getTime() >= from.getTime()) {
      return {
        from: formatTimeVN(inRaw),
        to: formatTimeVN(outRaw),
        source: det.berth_out_time ? 'neo đậu' : 'xuất hiện',
      };
    }
  }
  const startRaw = det.start_time;
  const endRaw = det.end_time;
  if (startRaw && endRaw) {
    const from = parseApiDate(startRaw);
    const to = parseApiDate(endRaw);
    if (from && to && to.getTime() >= from.getTime()) {
      return { from: formatTimeVN(startRaw), to: formatTimeVN(endRaw), source: 'xuất hiện' };
    }
  }
  return null;
}
