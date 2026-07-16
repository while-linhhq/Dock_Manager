import { useMemo, useState } from 'react';

export type SortDirection = 'asc' | 'desc';

export type SortState = {
  /** Khóa cột đang sắp xếp; null = giữ thứ tự gốc. */
  key: string | null;
  direction: SortDirection;
};

/** Bộ truy xuất giá trị mỗi cột: sortKey -> hàm lấy value từ row. */
export type SortAccessors<T> = Record<string, (row: T) => unknown>;

/**
 * So sánh 2 value bất kỳ. null/undefined LUÔN dồn xuống cuối (cả asc lẫn desc).
 * Number so trực tiếp; Date theo timestamp; còn lại localeCompare tiếng Việt,
 * numeric-aware (SG-10211 > SG-6898 đúng số học, không so từng ký tự).
 */
function baseCompare(a: unknown, b: unknown): number {
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  if (a instanceof Date && b instanceof Date) return a.getTime() - b.getTime();
  if (typeof a === 'boolean' && typeof b === 'boolean') {
    return a === b ? 0 : a ? 1 : -1;
  }
  return String(a).localeCompare(String(b), 'vi', { numeric: true, sensitivity: 'base' });
}

/**
 * Sắp xếp thuần (pure) — không phụ thuộc React, test được độc lập.
 * Không mutate mảng gốc. key=null -> giữ nguyên thứ tự.
 */
export function sortRows<T>(rows: T[], accessors: SortAccessors<T>, sort: SortState): T[] {
  const acc = sort.key ? accessors[sort.key] : undefined;
  if (!acc) return rows;
  const dir = sort.direction === 'asc' ? 1 : -1;
  return [...rows].sort((ra, rb) => {
    const av = acc(ra);
    const bv = acc(rb);
    const an = av == null || av === '';
    const bn = bv == null || bv === '';
    if (an && bn) return 0;
    if (an) return 1; // giá trị rỗng luôn xuống cuối
    if (bn) return -1;
    return baseCompare(av, bv) * dir;
  });
}

/**
 * Sắp xếp client-side cho bảng. Trả mảng đã sort (không mutate gốc),
 * state hiện tại, và toggle: click cùng cột -> đảo chiều; cột khác -> asc.
 */
export function useTableSort<T>(
  rows: T[],
  accessors: SortAccessors<T>,
  initial: SortState = { key: null, direction: 'asc' },
) {
  const [sort, setSort] = useState<SortState>(initial);

  const sorted = useMemo(() => sortRows(rows, accessors, sort), [rows, sort, accessors]);

  const toggle = (key: string) => {
    setSort((prev) =>
      prev.key === key
        ? { key, direction: prev.direction === 'asc' ? 'desc' : 'asc' }
        : { key, direction: 'asc' },
    );
  };

  return { sorted, sort, toggle, setSort };
}
