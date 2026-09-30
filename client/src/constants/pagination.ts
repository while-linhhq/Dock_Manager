/** Kích thước trang dùng chung cho mọi bảng phân trang phía server. */
export const PAGE_SIZE_OPTIONS = [25, 50, 100, 200] as const;

/** Kích thước trang mặc định (khớp server: limit tối đa 200). */
export const DEFAULT_PAGE_SIZE = 50;
