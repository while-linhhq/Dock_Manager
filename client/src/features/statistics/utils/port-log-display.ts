import type { PortLogRead } from '../../../types/api.types';
import { formatDateTimeVN } from '../../../utils/date-time';

export const PORT_LOG_TABLE_COL_COUNT = 10;

export function portLogShip(log: PortLogRead) {
  return log.voted_ship_id ?? log.ship_id ?? '';
}

export function portLogTimeIso(log: PortLogRead) {
  return log.logged_at ?? log.log_date ?? null;
}

export function fmtDateTime(s: string | null | undefined) {
  if (s == null || s === '') {
    return '—';
  }
  return formatDateTimeVN(s);
}

export function fmtNullableStr(s: string | null | undefined) {
  if (s == null || s === '') {
    return 'null';
  }
  return s;
}

export function fmtConf(n: number | null | undefined) {
  if (n == null || Number.isNaN(Number(n))) {
    return 'null';
  }
  return Number(n).toFixed(4);
}

export function fmtInt(n: number | null | undefined) {
  if (n == null || Number.isNaN(Number(n))) {
    return '—';
  }
  return String(n);
}

type VoteEntry = { count?: number; total_conf?: number };

export function formatVoteSummary(log: PortLogRead): string {
  const v = log.vote_summary;
  if (v == null || typeof v !== 'object' || Object.keys(v).length === 0) {
    return '{}';
  }
  const lines: string[] = [];
  for (const [shipId, raw] of Object.entries(v)) {
    const o = raw as VoteEntry;
    const c = o?.count ?? 0;
    const tc = o?.total_conf ?? 0;
    lines.push(`${shipId}: count=${c}, total_conf=${Number(tc).toFixed(4)}`);
  }
  return lines.join('\n');
}
