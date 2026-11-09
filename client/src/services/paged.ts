/** Tham số query cho các endpoint danh sách phân trang. */
export type PagedQueryParams = Record<string, string | number | boolean | undefined | null>;

/** Kết quả phân trang: mảng bản ghi (server trả mảng trần) + tổng số bản ghi. */
export type PagedResult<T> = {
  items: T[];
  total: number;
};

/**
 * Dựng query string từ object tham số: bỏ qua `undefined`/`null`,
 * encode bằng URLSearchParams. Trả `''` khi không có tham số nào.
 */
export function buildQuery(params?: PagedQueryParams): string {
  if (!params) {
    return '';
  }

  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) {
      continue;
    }
    search.set(key, String(value));
  }

  const query = search.toString();
  return query ? `?${query}` : '';
}

/**
 * Đọc tổng số bản ghi từ header `X-Total-Count`.
 * Header thiếu/không parse được ⇒ fallback về số bản ghi của trang hiện tại
 * để UI suy giảm chứ không vỡ. Chỉ nhận chuỗi toàn chữ số (sau khi trim):
 * `'12.5'`, `'12abc'`, `'-1'`, `''` đều rơi về fallback.
 */
export function parseTotalCount(rawValue: string | null, fallback: number): number {
  if (rawValue === null) {
    return fallback;
  }

  const trimmed = rawValue.trim();
  if (!/^\d+$/.test(trimmed)) {
    return fallback;
  }

  const parsed = Number.parseInt(trimmed, 10);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }

  return parsed;
}
