import React from 'react';
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Loader2,
  MoreVertical,
  Plus,
  Trash2,
} from 'lucide-react';
import { DataPagination } from '../../../components/DataPagination';
import { Button } from '../../../components/Button/Button';
import { cn } from '../../../utils/cn';
import { dt } from '../../../utils/data-table-classes';
import { formatDateTimeVN } from '../../../utils/date-time';
import type { OrderRead, VesselRead, VesselTypeRead } from '../../../types/api.types';
import {
  FilterField,
  TableFilterPanel,
  filterControlClass,
} from '../../../components/TableFilterPanel/TableFilterPanel';
import {
  isOrderSortKey,
  type OrderSort,
} from '../services/ordersApi';
import {
  normOrderStatus,
  statusColors,
  statusLabels,
} from '../utils/order-status-display';
import { SortableTh } from '../../../components/SortableTh/SortableTh';
import {
  useTableSort,
  type SortAccessors,
  type SortDirection,
  type SortState,
} from '../../../hooks/useTableSort';

export type OrdersListSectionProps = {
  orderQ: string;
  setOrderQ: (v: string) => void;
  orderStatusFilter: string;
  setOrderStatusFilter: (v: string) => void;
  orderShipIdFilter: string;
  setOrderShipIdFilter: (v: string) => void;
  orderVesselTypeFilter: string;
  setOrderVesselTypeFilter: (v: string) => void;
  orderDateFrom: string;
  setOrderDateFrom: (v: string) => void;
  orderDateTo: string;
  setOrderDateTo: (v: string) => void;
  orderMinAmt: string;
  setOrderMinAmt: (v: string) => void;
  orderMaxAmt: string;
  setOrderMaxAmt: (v: string) => void;
  resetOrderFilters: () => void;
  orderFilterCount: number;
  onOpenCreate: () => void;
  /** Đúng MỘT trang đơn hàng lấy từ server (không phải toàn bộ tập kết quả). */
  orders: OrderRead[];
  vessels: VesselRead[];
  vesselTypes: VesselTypeRead[];
  isLoading: boolean;
  error: string | null;
  /** Phân trang phía server — state do `usePagedQuery` ở `OrdersView` giữ. */
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
  /** Đổi cột sắp xếp → server nạp lại trang 1 với `sort`/`order` mới. */
  onSortChange: (sort: OrderSort) => void;
  onEdit: (order: OrderRead) => void;
  onDelete: (id: string) => void;
};

/**
 * Mặc định của bảng: không cột nào được chọn nên không gửi `sort`/`order` —
 * server trả về đúng thứ tự `created_at desc` như trước.
 */
const INITIAL_ORDER_SORT: SortState = { key: null, direction: 'asc' };

export const OrdersListSection: React.FC<OrdersListSectionProps> = ({
  orderQ,
  setOrderQ,
  orderStatusFilter,
  setOrderStatusFilter,
  orderShipIdFilter,
  setOrderShipIdFilter,
  orderVesselTypeFilter,
  setOrderVesselTypeFilter,
  orderDateFrom,
  setOrderDateFrom,
  orderDateTo,
  setOrderDateTo,
  orderMinAmt,
  setOrderMinAmt,
  orderMaxAmt,
  setOrderMaxAmt,
  resetOrderFilters,
  orderFilterCount,
  onOpenCreate,
  orders,
  vessels,
  vesselTypes,
  isLoading,
  error,
  page,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
  onSortChange,
  onEdit,
  onDelete,
}) => {
  // Sắp xếp do SERVER thực hiện: `useTableSort` chỉ giữ trạng thái mũi tên trên
  // tiêu đề (`sorted` không dùng — thứ tự trong trang là của server).
  const sortAccessors: SortAccessors<OrderRead> = {
    order_code: (order) => String(order.id),
    vessel: (order) => order.vessel?.ship_id ?? '',
    created_at: (order) => order.created_at ?? '',
    status: (order) => normOrderStatus(String(order.status ?? 'pending')),
    total_amount: (order) => Number(order.total_amount ?? 0),
  };
  const { sort, setSort } = useTableSort(orders, sortAccessors, INITIAL_ORDER_SORT);

  /**
   * Đổi cột/chiều: cập nhật mũi tên trên tiêu đề rồi báo server nạp lại trang 1
   * với `sort`/`order` mới (khóa cột trùng whitelist của API đơn hàng).
   */
  const handleSortChange = (key: string) => {
    if (!isOrderSortKey(key)) {
      return;
    }
    const direction: SortDirection =
      sort.key === key && sort.direction === 'asc' ? 'desc' : 'asc';
    setSort({ key, direction });
    onSortChange({ key, order: direction });
  };

  return (
    <>
      <TableFilterPanel onReset={resetOrderFilters} activeCount={orderFilterCount}>
        <FilterField label="Từ khóa (mã đơn / tàu / hàng hóa)">
          <input
            type="text"
            value={orderQ}
            onChange={(e) => setOrderQ(e.target.value)}
            placeholder="Lọc nhanh..."
            className={filterControlClass}
          />
        </FilterField>
        <FilterField label="Trạng thái">
          <select
            value={orderStatusFilter}
            onChange={(e) => setOrderStatusFilter(e.target.value)}
            className={filterControlClass}
          >
            <option value="">Tất cả</option>
            {Object.entries(statusLabels).map(([val, label]) => (
              <option key={val} value={val}>
                {label}
              </option>
            ))}
          </select>
        </FilterField>
        <FilterField label="Mã tàu">
          <select
            value={orderShipIdFilter}
            onChange={(e) => setOrderShipIdFilter(e.target.value)}
            className={filterControlClass}
          >
            <option value="">Tất cả</option>
            {vessels.map((vessel) => (
              <option key={vessel.id} value={String(vessel.id)}>
                {vessel.ship_id}
              </option>
            ))}
          </select>
        </FilterField>
        <FilterField label="Loại tàu">
          <select
            value={orderVesselTypeFilter}
            onChange={(e) => setOrderVesselTypeFilter(e.target.value)}
            className={filterControlClass}
          >
            <option value="">Tất cả</option>
            {vesselTypes.map((type) => (
              <option key={type.id} value={String(type.id)}>
                {type.type_name}
              </option>
            ))}
          </select>
        </FilterField>
        <FilterField label="Từ ngày tạo">
          <input
            type="date"
            value={orderDateFrom}
            onChange={(e) => setOrderDateFrom(e.target.value)}
            className={filterControlClass}
          />
        </FilterField>
        <FilterField label="Đến ngày tạo">
          <input
            type="date"
            value={orderDateTo}
            onChange={(e) => setOrderDateTo(e.target.value)}
            className={filterControlClass}
          />
        </FilterField>
        <FilterField label="Số tiền tối thiểu (₫)">
          <input
            type="number"
            min={0}
            value={orderMinAmt}
            onChange={(e) => setOrderMinAmt(e.target.value)}
            placeholder="0"
            className={filterControlClass}
          />
        </FilterField>
        <FilterField label="Số tiền tối đa (₫)">
          <input
            type="number"
            min={0}
            value={orderMaxAmt}
            onChange={(e) => setOrderMaxAmt(e.target.value)}
            placeholder="Không giới hạn"
            className={filterControlClass}
          />
        </FilterField>
      </TableFilterPanel>

      <div className="flex flex-wrap items-center justify-end gap-3">
        {error && <p className="mr-auto text-[12px] normal-case text-red-500">{error}</p>}
        <Button
          type="button"
          onClick={onOpenCreate}
          className="bg-blue-600 hover:bg-blue-700 text-white shadow-lg shadow-blue-600/20"
        >
          <Plus className="w-4 h-4 mr-2" />
          Tạo Đơn Hàng
        </Button>
      </div>

      <div className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 rounded-2xl shadow-2xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className={dt.headRow}>
                <SortableTh sortKey="order_code" sort={sort} onSort={handleSortChange}>
                  Mã Đơn
                </SortableTh>
                <SortableTh sortKey="vessel" sort={sort} onSort={handleSortChange}>
                  Tàu / Hàng Hóa
                </SortableTh>
                <SortableTh sortKey="created_at" sort={sort} onSort={handleSortChange}>
                  Thời Gian
                </SortableTh>
                <SortableTh sortKey="status" sort={sort} onSort={handleSortChange}>
                  Trạng Thái
                </SortableTh>
                <SortableTh sortKey="total_amount" sort={sort} onSort={handleSortChange}>
                  Số Tiền
                </SortableTh>
                <th className={cn(dt.pad, 'text-right')}>Thao Tác</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-white/5">
              {isLoading && orders.length === 0 ? (
                <tr>
                  <td colSpan={6} className={cn(dt.pad, 'py-12 text-center')}>
                    <Loader2 className="w-8 h-8 animate-spin text-blue-500 mx-auto mb-2" />
                    <span className={cn('font-mono uppercase', dt.empty)}>Đang tải dữ liệu...</span>
                  </td>
                </tr>
              ) : orders.length > 0 ? (
                orders.map((order) => {
                  const st = normOrderStatus(String(order.status ?? 'pending'));
                  return (
                    <tr
                      key={order.id}
                      className="hover:bg-gray-50 dark:hover:bg-white/[0.02] transition-colors group"
                    >
                      <td className={dt.pad}>
                        <span className={dt.monoAccent}>{String(order.id).split('-')[0]}</span>
                      </td>
                      <td className={dt.pad}>
                        <div className="flex flex-col gap-0.5">
                          <span className={cn(dt.body, 'font-bold uppercase')}>
                            {order.vessel?.ship_id || 'KHÔNG XÁC ĐỊNH'}
                          </span>
                          <span className={cn(dt.bodyMuted, 'uppercase tracking-tight text-xs')}>
                            {order.cargo_details || 'Chi tiết hàng hóa'}
                          </span>
                        </div>
                      </td>
                      <td className={dt.pad}>
                        <div
                          className={cn('flex items-center', dt.mono, 'text-gray-500 dark:text-gray-400')}
                        >
                          <Clock className="w-3.5 h-3.5 mr-1.5 shrink-0 opacity-50" />
                          {formatDateTimeVN(order.created_at)}
                        </div>
                      </td>
                      <td className={dt.pad}>
                        <span
                          className={cn(
                            'inline-flex items-center px-2.5 py-1 rounded-full border',
                            dt.badge,
                            statusColors[st] || statusColors.pending,
                          )}
                        >
                          {st === 'completed' && (
                            <CheckCircle2 className="w-3.5 h-3.5 mr-1 shrink-0" />
                          )}
                          {st === 'pending' && <Clock className="w-3.5 h-3.5 mr-1 shrink-0" />}
                          {st === 'cancelled' && <AlertCircle className="w-3.5 h-3.5 mr-1 shrink-0" />}
                          {statusLabels[st] || order.status}
                        </span>
                      </td>
                      <td className={dt.pad}>
                        <span className={cn(dt.mono, 'font-bold text-gray-900 dark:text-white')}>
                          {Number(order.total_amount ?? 0).toLocaleString('vi-VN')} ₫
                        </span>
                      </td>
                      <td className={cn(dt.pad, 'text-right')}>
                        <div className="inline-flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => onEdit(order)}
                            className="p-2 hover:bg-gray-100 dark:hover:bg-white/10 rounded-lg transition-all text-gray-500 hover:text-gray-900 dark:hover:text-white"
                          >
                            <MoreVertical className="w-4 h-4" />
                          </button>
                          <button
                            type="button"
                            onClick={() => onDelete(String(order.id))}
                            className="p-2 hover:bg-red-100 dark:hover:bg-red-500/10 rounded-lg transition-all text-red-500"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td
                    colSpan={6}
                    className={cn(
                      dt.pad,
                      'py-12 text-center font-mono uppercase tracking-wide',
                      dt.empty,
                    )}
                  >
                    {total === 0
                      ? orderFilterCount > 0
                        ? 'Không có đơn hàng khớp bộ lọc'
                        : 'Không có đơn hàng nào'
                      : 'Trang này không có đơn hàng'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <DataPagination
          page={page}
          pageSize={pageSize}
          total={total}
          onPageChange={onPageChange}
          onPageSizeChange={onPageSizeChange}
        />
      </div>
    </>
  );
};
