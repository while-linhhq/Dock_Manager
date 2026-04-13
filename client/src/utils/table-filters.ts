import { parseApiDate } from './date-time';

/** Local calendar day bounds for filtering ISO timestamps from the API. */
export function dayStartMs(isoDate: string): number {
  if (!isoDate) {
    return NaN;
  }
  return new Date(`${isoDate}T00:00:00`).getTime();
}

export function dayEndMs(isoDate: string): number {
  if (!isoDate) {
    return NaN;
  }
  return new Date(`${isoDate}T23:59:59.999`).getTime();
}

export function isoInLocalDateRange(
  iso: string | null | undefined,
  from: string,
  to: string,
): boolean {
  if (!from && !to) {
    return true;
  }
  if (!iso) {
    return false;
  }
  const parsed = parseApiDate(iso);
  const t = parsed ? parsed.getTime() : NaN;
  if (Number.isNaN(t)) {
    return false;
  }
  if (from) {
    const f = dayStartMs(from);
    if (!Number.isNaN(f) && t < f) {
      return false;
    }
  }
  if (to) {
    const e = dayEndMs(to);
    if (!Number.isNaN(e) && t > e) {
      return false;
    }
  }
  return true;
}

export function textMatches(haystack: string | null | undefined, needle: string): boolean {
  const n = needle.trim().toLowerCase();
  if (!n) {
    return true;
  }
  const h = (haystack ?? '').toString().toLowerCase();
  return h.includes(n);
}

/** OR match: needle empty → true; else any field contains needle (case-insensitive). */
export function matchesAnyField(
  needle: string,
  ...haystacks: (string | number | null | undefined)[]
): boolean {
  const n = needle.trim().toLowerCase();
  if (!n) {
    return true;
  }
  return haystacks.some((h) =>
    (h ?? '').toString().toLowerCase().includes(n),
  );
}
