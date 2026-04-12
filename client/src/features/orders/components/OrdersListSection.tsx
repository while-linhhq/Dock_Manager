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
import { Button } from '../../../components/Button/Button';
import { cn } from '../../../utils/cn';
import { dt } from '../../../utils/data-table-classes';
import type { OrderRead } from '../../../types/api.types';
import {
  FilterField,
  TableFilterPanel,
  filterControlClass,
} from '../../../components/TableFilterPanel/TableFilterPanel';
import {
  normOrderStatus,
  statusColors,
  statusLabels,
} from '../utils/order-status-display';
import { OrdersActivityIndicator } from './OrdersActivityIndicator';

export type OrdersListSectionProps = {
  orderQ: string;
  setOrderQ: (v: string) => void;
  orderStatusFilter: string;
  setOrderStatusFilter: (v: string) => void;
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
  orders: OrderRead[];
  filteredOrders: OrderRead[];
  isLoading: boolean;
  onEdit: (order: OrderRead) => void;
  onDelete: (id: string) => void;
};

export const OrdersListSection: React.FC<OrdersListSectionProps> = ({
  orderQ,
  setOrderQ,
  orderStatusFilter,
  setOrderStatusFilter,
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
  filteredOrders,
  isLoading,
  onEdit,
  onDelete,
}) => {
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

      <div className="flex justify-end">
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
                <th className={dt.pad}>Mã Đơn</th>
                <th className={dt.pad}>Tàu / Hàng Hóa</th>
                <th className={dt.pad}>Thời Gian</th>
                <th className={dt.pad}>Trạng Thái</th>
                <th className={dt.pad}>Số Tiền</th>
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
              ) : filteredOrders.length > 0 ? (
                filteredOrders.map((order) => {
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
                          {new Date(order.created_at).toLocaleString('vi-VN')}
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
                          {st === 'processing' && <OrdersActivityIndicator />}
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
                    {orders.length === 0
                      ? 'Không có đơn hàng nào'
                      : 'Không có đơn hàng khớp bộ lọc'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="p-4 border-t border-gray-200 dark:border-white/5 flex items-center justify-between bg-gray-50 dark:bg-white/[0.01]">
          <p className="text-[10px] font-mono text-gray-500 uppercase">
            Hiển thị {filteredOrders.length}/{orders.length} đơn hàng
          </p>
          <div className="flex space-x-2">
            <Button
              variant="outline"
              size="sm"
              className="border-gray-200 dark:border-white/10 text-xs py-1 px-3 h-auto opacity-50 cursor-not-allowed"
            >
              Trước
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="border-gray-200 dark:border-white/10 text-xs py-1 px-3 h-auto"
            >
              Sau
            </Button>
          </div>
        </div>
      </div>
    </>
  );
};
