import { formatFeeConfigDisplay } from '../../../utils/fee-billing-unit';
import type { VesselRead, VesselTypeRead } from '../../../types/api.types';

export function resolveVesselTypeName(v: VesselRead, types: VesselTypeRead[]) {
  if (v.vessel_type?.type_name) {
    return v.vessel_type.type_name;
  }
  if (v.vessel_type_id == null || v.vessel_type_id === '') {
    return '—';
  }
  const idStr = String(v.vessel_type_id);
  return types.find((t) => String(t.id) === idStr)?.type_name ?? '—';
}

export function formatApplicableFee(v: VesselRead) {
  const f = v.applicable_fee;
  if (!f) {
    return '—';
  }
  return `${f.fee_name} — ${formatFeeConfigDisplay(f.base_fee, f.unit)}`;
}
