import React from 'react';
import { ChevronDown, ChevronUp, ChevronsUpDown } from 'lucide-react';
import { cn } from '../../utils/cn';
import { dt } from '../../utils/data-table-classes';
import type { SortState } from '../../hooks/useTableSort';

export type SortableThProps = {
  /** Khóa cột — khớp key trong SortAccessors. */
  sortKey: string;
  /** Trạng thái sort hiện tại của bảng. */
  sort: SortState;
  /** Gọi khi click header để đổi cột/chiều. */
  onSort: (key: string) => void;
  children: React.ReactNode;
  /** className phụ (vd căn phải cột số, độ rộng). */
  className?: string;
  /** Căn nội dung header: mặc định trái. */
  align?: 'left' | 'center' | 'right';
};

/**
 * Ô <th> có thể sắp xếp: hiện mũi tên nhỏ (▲/▼) khi đang sort theo cột này,
 * mũi tên mờ 2 chiều khi chưa sort. Click để toggle asc → desc → asc.
 * Dùng chung cho MỌI bảng dữ liệu trong app.
 */
export const SortableTh: React.FC<SortableThProps> = ({
  sortKey,
  sort,
  onSort,
  children,
  className,
  align = 'left',
}) => {
  const active = sort.key === sortKey;
  const justify =
    align === 'right' ? 'justify-end' : align === 'center' ? 'justify-center' : 'justify-start';

  return (
    <th className={cn(dt.pad, className)} aria-sort={active ? (sort.direction === 'asc' ? 'ascending' : 'descending') : 'none'}>
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        className={cn(
          'group inline-flex items-center gap-1.5 select-none transition-colors w-full',
          justify,
          active
            ? 'text-blue-600 dark:text-blue-400'
            : 'hover:text-gray-700 dark:hover:text-gray-200',
        )}
        title="Bấm để sắp xếp"
      >
        <span>{children}</span>
        {active ? (
          sort.direction === 'asc' ? (
            <ChevronUp className="w-3.5 h-3.5 shrink-0" />
          ) : (
            <ChevronDown className="w-3.5 h-3.5 shrink-0" />
          )
        ) : (
          <ChevronsUpDown className="w-3.5 h-3.5 shrink-0 opacity-30 group-hover:opacity-60" />
        )}
      </button>
    </th>
  );
};
