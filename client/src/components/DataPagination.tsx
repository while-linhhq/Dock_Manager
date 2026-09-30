import { useRef, useState, type MouseEvent } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { cn } from '../utils/cn';
import { filterControlClass } from './TableFilterPanel/TableFilterPanel';
import { PAGE_SIZE_OPTIONS } from '../constants/pagination';

// Hằng số dùng chung được khai báo ở `constants/pagination.ts`; re-export tại đây
// để nơi dùng có thể import kèm component.
export { DEFAULT_PAGE_SIZE, PAGE_SIZE_OPTIONS } from '../constants/pagination';

export type DataPaginationProps = {
  /** Trang hiện tại, tính từ 1. */
  page: number;
  pageSize: number;
  /** Tổng số bản ghi trên toàn bộ tập kết quả (không phải số dòng của trang). */
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
};

const navButtonClass =
  'inline-flex items-center gap-1 rounded-lg border border-gray-200 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-gray-600 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40 dark:border-white/10 dark:text-gray-300 dark:hover:bg-white/5';

/**
 * Footer phân trang dùng chung cho các bảng phân trang phía server.
 * `usePagedQuery` đã tự lùi về trang cuối khi trang hiện tại không còn tồn tại;
 * ở đây vẫn xử lý phòng thủ trường hợp `page` vượt quá trang cuối (bảng rỗng +
 * đúng tổng số, không hiện dải ngược 201–120, không phải lỗi).
 */
export function DataPagination({
  page,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
}: DataPaginationProps) {
  // Ô nhập số trang giữ draft riêng để gõ tự do; chỉ chốt khi Enter/blur.
  const [pageDraft, setPageDraft] = useState<string | null>(null);
  // Bấm nút chuyển trang trong lúc ô nhập còn draft: blur xảy ra TRƯỚC click
  // (mousedown → blur → click) và React flush state của blur ngay, nên nếu để
  // blur chốt draft thì cú click sẽ tính tiếp từ trang vừa chốt (gõ 3 rồi bấm
  // "Sau" sẽ nhảy 3 → 4). Cờ này để blur bỏ draft thay vì chốt nó.
  const skipDraftCommitRef = useRef(false);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const isOutOfRange = total > 0 && page > totalPages;
  const rangeFrom = total > 0 && !isOutOfRange ? (page - 1) * pageSize + 1 : 0;
  const rangeTo = isOutOfRange ? 0 : Math.min(page * pageSize, total);

  const rangeLabel =
    total === 0
      ? 'Không có bản ghi'
      : isOutOfRange
        ? `Hiển thị 0 / ${total} bản ghi`
        : `Hiển thị ${rangeFrom}–${rangeTo} / ${total} bản ghi`;

  const commitPageDraft = () => {
    if (skipDraftCommitRef.current) {
      skipDraftCommitRef.current = false;
      setPageDraft(null);
      return;
    }

    const parsed = Number.parseInt((pageDraft ?? '').trim(), 10);
    setPageDraft(null);
    if (!Number.isFinite(parsed)) {
      return;
    }
    onPageChange(Math.min(Math.max(1, parsed), totalPages));
  };

  // Nút chuyển trang: bỏ draft đang gõ dở rồi điều hướng từ trang đang hiển thị.
  const goToPage = (next: number) => {
    setPageDraft(null);
    onPageChange(next);
  };

  // Cờ chỉ sống trong một lần bấm nút: bật ở mousedown (trước blur) và tắt lại ở
  // mouseup/mouseleave để trường hợp bấm rồi kéo ra ngoài không làm treo cờ — nếu
  // treo, lần gõ số trang sau đó sẽ bị blur bỏ qua một cách khó hiểu. Chỉ bật với
  // chuột TRÁI: bấm chuột phải rồi thả ra ngoài không phát mouseup/mouseleave nên
  // cờ sẽ treo lại.
  const navDraftGuard = {
    onMouseDown: (e: MouseEvent) => {
      if (e.button === 0) {
        skipDraftCommitRef.current = true;
      }
    },
    onMouseUp: () => {
      skipDraftCommitRef.current = false;
    },
    onMouseLeave: () => {
      skipDraftCommitRef.current = false;
    },
  };

  return (
    <div className="flex flex-col gap-3 border-t border-gray-100 dark:border-white/5 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-center gap-3 text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-400">
        <span>{rangeLabel}</span>
        <label className="flex items-center gap-1.5 normal-case">
          <span>Mỗi trang</span>
          <select
            value={pageSize}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
            className="rounded-md border border-gray-200 bg-transparent px-1.5 py-1 text-xs dark:border-white/10"
          >
            {PAGE_SIZE_OPTIONS.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          {...navDraftGuard}
          onClick={() => goToPage(Math.max(1, page - 1))}
          disabled={page <= 1}
          className={navButtonClass}
        >
          <ChevronLeft className="h-4 w-4" />
          Trước
        </button>
        <span className="text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
          Trang {page} / {totalPages}
        </span>
        <label className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-400">
          <span className="normal-case">Đến trang</span>
          <input
            type="number"
            min={1}
            max={totalPages}
            inputMode="numeric"
            aria-label="Số trang"
            value={pageDraft ?? String(page)}
            onChange={(e) => setPageDraft(e.target.value)}
            onBlur={commitPageDraft}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                commitPageDraft();
              }
            }}
            className={cn(filterControlClass, 'w-16 px-2 py-1 text-xs')}
          />
        </label>
        <button
          type="button"
          {...navDraftGuard}
          onClick={() => goToPage(Math.min(totalPages, page + 1))}
          disabled={page >= totalPages}
          className={navButtonClass}
        >
          Sau
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
