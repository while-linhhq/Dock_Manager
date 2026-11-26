export const APP_TIME_ZONE = 'Asia/Ho_Chi_Minh';

/** Form values are Vietnam wall time, never the browser's timezone. */
export function apiToVietnamInput(value?: string | null): string {
  const date = parseApiDate(value);
  if (!date) return '';
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: APP_TIME_ZONE, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
  }).formatToParts(date);
  const p = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}:${p.second}`;
}

export function vietnamInputToApi(value: string): string | null {
  if (!value.trim()) return null;
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?$/.test(value)) {
    throw new Error('Thời gian không hợp lệ');
  }
  const date = new Date(`${value}+07:00`);
  const canonical = value.length === 16 ? `${value}:00` : value;
  if (Number.isNaN(date.getTime()) || apiToVietnamInput(date.toISOString()) !== canonical) {
    throw new Error('Thời gian không hợp lệ');
  }
  return date.toISOString();
}

function hasExplicitTimezone(input: string): boolean {
  return /(?:Z|[+-]\d{2}:\d{2})$/i.test(input.trim());
}

/**
 * Parse API datetime safely.
 * - If backend string has no timezone suffix, treat it as UTC.
 */
export function parseApiDate(
  value: string | Date | null | undefined,
): Date | null {
  if (value == null) {
    return null;
  }
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value;
  }
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const normalized = hasExplicitTimezone(trimmed) ? trimmed : `${trimmed}Z`;
  const d = new Date(normalized);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function formatDateTimeVN(
  value: string | Date | null | undefined,
  options?: Intl.DateTimeFormatOptions,
): string {
  const d = parseApiDate(value);
  if (!d) {
    return '—';
  }
  return d.toLocaleString('vi-VN', {
    timeZone: APP_TIME_ZONE,
    ...options,
  });
}

export function formatTimeVN(
  value: string | Date | null | undefined,
  options?: Intl.DateTimeFormatOptions,
): string {
  const d = parseApiDate(value);
  if (!d) {
    return '—';
  }
  return d.toLocaleTimeString('vi-VN', {
    timeZone: APP_TIME_ZONE,
    hour12: false,
    ...options,
  });
}
