import type { FeeConfigRead, VesselTypeRead } from '../../../types/api.types';

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
