import { useCallback, useEffect, useRef, useState } from 'react';
import { DEFAULT_PAGE_SIZE } from '../constants/pagination';

/** Tham số hook truyền cho `fetcher` mỗi lần gọi API. */
export type PagedQueryRequest<F, S> = {
  /** Số bản ghi bỏ qua: `(page - 1) * pageSize`. */
  skip: number;
  /** Kích thước trang hiện tại. */
  limit: number;
  filters: F;
  sort?: S;
};

export type PagedQueryFetcher<T, F, S> = (
  request: PagedQueryRequest<F, S>,
) => Promise<{ items: T[]; total: number }>;

export type UsePagedQueryOptions<T, F, S> = {
  fetcher: PagedQueryFetcher<T, F, S>;
  initialPageSize?: number;
  /** Giá trị khởi tạo của bộ lọc (đổi prop này KHÔNG tự động refetch). */
  filters?: F;
  /** Giá trị khởi tạo của sắp xếp (đổi prop này KHÔNG tự động refetch). */
  sort?: S;
  /** Thời gian chờ trước khi gọi lại khi `filters`/`sort` đổi (mặc định 300ms). */
  debounceMs?: number;
};

export type UsePagedQueryResult<T, F, S> = {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
  isLoading: boolean;
  error: string | null;
  setPage: (page: number) => void;
  setPageSize: (size: number) => void;
  setFilters: (filters: F) => void;
  setSort: (sort: S) => void;
  reload: () => void;
};

function resolveErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  if (typeof error === 'string' && error) {
    return error;
  }
  return 'Không tải được dữ liệu';
}

/**
 * Phân trang phía server dùng chung: giữ `page`/`pageSize`/`filters`/`sort`,
 * gọi `fetcher` với `skip = (page - 1) * pageSize`, debounce khi bộ lọc/sắp xếp
 * đổi, và bỏ qua kết quả của request cũ (chống race).
 *
 * Sau mỗi lần nạp thành công, nếu `total` mới khiến trang hiện tại không còn tồn
 * tại (`page > totalPages`) thì hook tự lùi về trang cuối và nạp lại — nên phía
 * consumer không bao giờ phải xử lý trang vượt quá giới hạn.
 *
 * `filters`/`sort` trong options chỉ là giá trị KHỞI TẠO (không theo dõi thay
 * đổi của prop): muốn đổi bộ lọc/sắp xếp thì gọi `setFilters`/`setSort` —
 * hai hàm này tự đưa `page` về 1.
 */
export function usePagedQuery<T, F = Record<string, unknown>, S = string>(
  options: UsePagedQueryOptions<T, F, S>,
): UsePagedQueryResult<T, F, S> {
  const {
    fetcher,
    initialPageSize = DEFAULT_PAGE_SIZE,
    filters: initialFilters,
    sort: initialSort,
    debounceMs = 300,
  } = options;

  const [items, setItems] = useState<T[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPageState] = useState(1);
  const [pageSize, setPageSizeState] = useState(initialPageSize);
  const [filters, setFiltersState] = useState<F>(() => initialFilters ?? ({} as F));
  const [sort, setSortState] = useState<S | undefined>(initialSort);
  // Tăng ở MỌI thao tác của người dùng (đổi trang/bộ lọc/sắp xếp/reload) để bảo
  // đảm effect luôn chạy lại, kể cả khi giá trị state không đổi.
  const [requestToken, setRequestToken] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const requestIdRef = useRef(0);
  const fetcherRef = useRef(fetcher);
  const prevFiltersRef = useRef(filters);
  const prevSortRef = useRef(sort);

  // `fetcher` thường là arrow function inline (identity mới mỗi render) nên giữ
  // qua ref để không kích hoạt refetch vô hạn.
  useEffect(() => {
    fetcherRef.current = fetcher;
  }, [fetcher]);

  /**
   * Bắt đầu một lần nạp mới: bật loading + xoá lỗi NGAY trong event handler (trước
   * cả debounce) để consumer không hiển thị số trang mới kèm dữ liệu của trang cũ,
   * đồng thời vô hiệu hoá mọi response đang bay.
   *
   * Chỉ tăng `requestIdRef` lúc timer chạy là chưa đủ: một response kịp resolve
   * trong khoảng debounce (hoặc ngay sau commit, trước khi passive effect flush)
   * vẫn khớp `requestId` và ghi dữ liệu cũ lên UI.
   *
   * Tăng `requestToken` bảo đảm effect luôn chạy lại kể cả khi giá trị state không
   * đổi, nên không bao giờ có request bị mồ côi làm treo cờ loading.
   */
  const beginRefetch = useCallback(() => {
    setIsLoading(true);
    setError(null);
    requestIdRef.current += 1;
    setRequestToken((token) => token + 1);
  }, []);

  useEffect(() => {
    const filtersChanged = prevFiltersRef.current !== filters;
    const sortChanged = prevSortRef.current !== sort;
    prevFiltersRef.current = filters;
    prevSortRef.current = sort;

    // Đổi bộ lọc/sắp xếp thì debounce; đổi trang/kích thước trang/reload thì gọi ngay.
    const delay = filtersChanged || sortChanged ? Math.max(0, debounceMs) : 0;
    let cancelled = false;

    const timer = setTimeout(() => {
      const requestId = ++requestIdRef.current;
      const skip = (page - 1) * pageSize;

      void (async () => {
        try {
          const result = await fetcherRef.current({
            skip,
            limit: pageSize,
            filters,
            sort,
          });
          if (cancelled || requestId !== requestIdRef.current) {
            return;
          }
          setItems(result.items);
          setTotal(result.total);

          // Trang hiện tại có thể không còn tồn tại sau khi dữ liệu co lại (vd xoá
          // dòng cuối của trang cuối) → lùi về trang cuối rồi nạp lại. Chỉ chạy khi
          // `page > totalPages` nên `page` luôn giảm: không thể lặp vô hạn.
          const totalPages = Math.max(1, Math.ceil(result.total / pageSize));
          if (page > totalPages) {
            beginRefetch();
            setPageState(totalPages);
          }
        } catch (err) {
          if (cancelled || requestId !== requestIdRef.current) {
            return;
          }
          setItems([]);
          setTotal(0);
          setError(resolveErrorMessage(err));
        } finally {
          if (!cancelled && requestId === requestIdRef.current) {
            setIsLoading(false);
          }
        }
      })();
    }, delay);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [page, pageSize, filters, sort, requestToken, debounceMs, beginRefetch]);

  const setPage = useCallback(
    (next: number) => {
      setPageState(Number.isFinite(next) ? Math.max(1, Math.floor(next)) : 1);
      beginRefetch();
    },
    [beginRefetch],
  );

  const setPageSize = useCallback(
    (next: number) => {
      setPageSizeState(next);
      setPageState(1); // Đổi kích thước trang ⇒ về trang 1.
      beginRefetch();
    },
    [beginRefetch],
  );

  const setFilters = useCallback(
    (next: F) => {
      setFiltersState(next);
      setPageState(1); // Đổi bộ lọc ⇒ về trang 1.
      beginRefetch();
    },
    [beginRefetch],
  );

  const setSort = useCallback(
    (next: S) => {
      setSortState(next);
      setPageState(1); // Đổi sắp xếp ⇒ về trang 1.
      beginRefetch();
    },
    [beginRefetch],
  );

  const reload = useCallback(() => {
    beginRefetch();
  }, [beginRefetch]);

  return {
    items,
    total,
    page,
    pageSize,
    isLoading,
    error,
    setPage,
    setPageSize,
    setFilters,
    setSort,
    reload,
  };
}
