import type { FeeConfigRead, VesselRead, VesselTypeRead } from '../../../types/api.types';

export function feeConfigVesselTypeLabel(fee: FeeConfigRead, types: VesselTypeRead[]): string {
  const nested = fee.vessel_type?.type_name?.trim();
  if (nested) {
    return nested;
  }
  if (fee.vessel_type_id == null) {
    return 'Tất cả';
  }
  const idStr = String(fee.vessel_type_id);
  return types.find((t) => String(t.id) === idStr)?.type_name ?? `Loại #${idStr}`;
}

/** Nhãn mã tàu gắn với fee (fee giờ theo mã tàu). */
export function feeConfigVesselLabel(fee: FeeConfigRead, vessels: VesselRead[] = []): string {
  const nestedShip = fee.vessel?.ship_id?.trim();
  if (nestedShip) {
    return fee.vessel?.name ? `${nestedShip} — ${fee.vessel.name}` : nestedShip;
  }
  if (fee.vessel_id == null) {
    return '—';
  }
  const idStr = String(fee.vessel_id);
  const match = vessels.find((v) => String(v.id) === idStr);
  if (match) {
    return match.name ? `${match.ship_id} — ${match.name}` : match.ship_id;
  }
  return `Tàu #${idStr}`;
}
