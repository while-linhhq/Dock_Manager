/**
 * Bộ bảo vệ «chỉ request mới nhất được ghi» cho những store tự viết dữ liệu của
 * trang đang xem vào state (store là nguồn render).
 *
 * `usePagedQuery` chỉ bỏ qua kết quả của request cũ SAU khi `fetcher` resolve:
 * nếu chính `fetcher` (store) đã ghi dòng của mình vào state trước đó thì bảng vẫn
 * giữ dòng của trang/bộ lọc cũ trong khi `page`, `total` và footer đã là của truy
 * vấn mới — ví dụ trang 3 chưa lọc (chậm) về sau trang 1 đã lọc (nhanh). Với thao
 * tác tiền, bảng lệch bộ lọc còn nguy hiểm hơn lỗi hiển thị: nút thanh toán hàng
 * loạt sẽ trả cho những hoá đơn không khớp bộ lọc đang bật.
 *
 * Mỗi nguồn dữ liệu phân trang dùng MỘT guard riêng, tạo một lần ở module của
 * store (`const pageGuard = createLatestGuard();`). Không dùng chung một biến đếm
 * toàn cục cho mọi store: khi đó một request của store khác bắt đầu giữa chừng sẽ
 * vô hiệu hoá oan request đang chờ của store này.
 *
 * Cách dùng trong store:
 *
 *   const seq = pageGuard.next();
 *   try {
 *     const page = await api.getPage(request);
 *     if (!pageGuard.isLatest(seq)) return page;   // request cũ: không ghi gì
 *     set({ items: page.items, isLoading: false });
 *     return page;
 *   } catch (err) {
 *     if (pageGuard.isLatest(seq)) set({ items: [], error: ..., isLoading: false });
 *     throw err;
 *   }
 */
export type LatestRequestGuard = {
  /** Cấp số thứ tự cho một request vừa bắt đầu; request này trở thành mới nhất. */
  next: () => number;
  /** `true` nếu `seq` vẫn là số mới nhất được cấp (chưa có request nào chen vào). */
  isLatest: (seq: number) => boolean;
};

export function createLatestGuard(): LatestRequestGuard {
  let latest = 0;
  return {
    next: () => {
      latest += 1;
      return latest;
    },
    isLatest: (seq) => seq === latest,
  };
}
