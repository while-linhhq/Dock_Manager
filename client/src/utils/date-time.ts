export const APP_TIME_ZONE = 'Asia/Ho_Chi_Minh';

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
