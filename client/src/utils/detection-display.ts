import type { DetectionRead } from '../types/api.types';

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
  const d = new Date(raw);
  return Number.isNaN(d.getTime()) ? null : raw;
}
