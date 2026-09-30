import React from 'react';
import { AlertTriangle } from 'lucide-react';

export type PageScopeNoticeAction = 'payment' | 'export';

export type PageScopeNoticeProps = {
  /** Số hoá đơn thao tác thực sự chạm tới — các dòng của trang đang tải. */
  shownCount: number;
  /** Tổng số hoá đơn khớp tab + bộ lọc hiện tại (server trả qua `X-Total-Count`). */
  filteredTotal: number;
  /** Thao tác bị thu hẹp theo trang — quyết định vế thứ hai của câu cảnh báo. */
  action: PageScopeNoticeAction;
};

/**
 * Cảnh báo phạm vi trang cho các thao tác tiền / xuất dữ liệu.
 *
 * Danh sách hoá đơn chỉ tải MỘT trang, nên khi tập khớp bộ lọc lớn hơn số dòng
 * đang hiển thị thì «Thanh toán tất cả» và «Xuất theo filter» chỉ chạm tới các
 * dòng của trang đó — trước đây client tải tới 1000 dòng nên hai thao tác này phủ
 * toàn bộ tập lọc. Không nói rõ thì người dùng tưởng đã thanh toán/xuất hết.
 * Chỉ render khi thực sự bị thu hẹp (`filteredTotal > shownCount`), nên trường
 * hợp tập lọc vừa đủ một trang (phổ biến) giữ nguyên câu chữ cũ.
 */
export const PageScopeNotice: React.FC<PageScopeNoticeProps> = ({
  shownCount,
  filteredTotal,
  action,
}) => {
  if (filteredTotal <= shownCount) {
    return null;
  }

  return (
    <div className="rounded-xl border border-amber-300 bg-amber-50 p-3 dark:border-amber-500/40 dark:bg-amber-500/10">
      <p className="flex items-start gap-2 text-[11px] leading-relaxed text-amber-800 dark:text-amber-200">
        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        <span>
          Chỉ <span className="font-bold">{shownCount}</span> trong tổng{' '}
          <span className="font-bold">{filteredTotal}</span> hoá đơn khớp bộ lọc hiện tại đang được
          tải.{' '}
          {action === 'payment'
            ? `Thao tác thanh toán chỉ áp dụng cho ${shownCount} hoá đơn đang hiển thị trên trang này.`
            : `Thao tác xuất Excel chỉ gồm ${shownCount} hoá đơn đang hiển thị trên trang này.`}
        </span>
      </p>
    </div>
  );
};
