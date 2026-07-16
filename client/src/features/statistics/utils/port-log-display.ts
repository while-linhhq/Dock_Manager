import type { PortLogRead } from '../../../types/api.types';
import { formatDateTimeVN } from '../../../utils/date-time';

export const PORT_LOG_TABLE_COL_COUNT = 11;

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

/** Two-pool evidence entry when _evidence key is present. */
type EmbeddingEntry = { count?: number; total_score?: number; avg_score?: number };

function formatOcrEvidenceEntry(shipId: string, raw: unknown): string {
  const o = raw as VoteEntry;
  const c = o?.count ?? 0;
  const tc = o?.total_conf ?? 0;
  return `OCR ${shipId}: count=${c}, total=${Number(tc).toFixed(4)}`;
}

function formatEmbeddingEvidenceEntry(shipId: string, raw: unknown): string {
  const e = raw as EmbeddingEntry;
  if (e?.total_score != null || e?.avg_score != null) {
    const total = e.total_score ?? 0;
    const avg = e.avg_score ?? 0;
    return `EMB ${shipId}: count=${e.count ?? 0}, total=${Number(total).toFixed(4)}, avg=${Number(avg).toFixed(4)}`;
  }
  return `EMB ${shipId}: ${JSON.stringify(raw)}`;
}

export function formatVoteSummary(log: PortLogRead): string {
  const v = log.vote_summary;
  if (v == null || typeof v !== 'object' || Object.keys(v).length === 0) {
    return '{}';
  }
  const lines: string[] = [];
  const { _evidence, ...legacyVotes } = v as Record<string, unknown>;

  // Legacy OCR votes first
  for (const [shipId, raw] of Object.entries(legacyVotes)) {
    const o = raw as VoteEntry;
    const c = o?.count ?? 0;
    const tc = o?.total_conf ?? 0;
    lines.push(`OCR ${shipId}: count=${c}, total=${Number(tc).toFixed(4)}`);
  }

  // Two-pool evidence
  if (_evidence && typeof _evidence === 'object') {
    const ev = _evidence as Record<string, Record<string, unknown>>;
    for (const [pool, entries] of Object.entries(ev)) {
      if (pool === 'ocr') {
        for (const [sid, raw] of Object.entries(entries)) {
          lines.push(formatOcrEvidenceEntry(sid, raw));
        }
      }
    }
    for (const [pool, entries] of Object.entries(ev)) {
      if (pool === 'embedding') {
        for (const [sid, raw] of Object.entries(entries)) {
          lines.push(formatEmbeddingEvidenceEntry(sid, raw));
        }
      }
    }
  }

  return lines.join('\n');
}
