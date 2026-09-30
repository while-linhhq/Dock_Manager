import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useOrderStore } from '../store/orderStore';
import { useVesselStore } from '../../vessels/store/vesselStore';
import type {
  OrderCreate,
  OrderFilters,
  OrderSort,
  OrderUpdate,
} from '../services/ordersApi';
import type { OrderRead } from '../../../types/api.types';
import { usePagedQuery } from '../../../hooks/usePagedQuery';
import { orderSchema } from '../orders-schemas';
import { OrdersListSection } from '../components/OrdersListSection';
import { OrderFormModal } from '../components/OrderFormModal';

export const OrdersView: React.FC = () => {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [orderQ, setOrderQ] = useState('');
  const [orderStatusFilter, setOrderStatusFilter] = useState('');
  const [orderShipIdFilter, setOrderShipIdFilter] = useState('');
  const [orderVesselTypeFilter, setOrderVesselTypeFilter] = useState('');
  const [orderDateFrom, setOrderDateFrom] = useState('');
  const [orderDateTo, setOrderDateTo] = useState('');
  const [orderMinAmt, setOrderMinAmt] = useState('');
  const [orderMaxAmt, setOrderMaxAmt] = useState('');

  const { isLoading, fetchOrdersPage, createOrder, updateOrder, deleteOrder } = useOrderStore();
  const { vessels, vesselTypes, fetchVessels, fetchVesselTypes } = useVesselStore();

  const form = useForm<OrderCreate>({
    resolver: zodResolver(orderSchema),
    defaultValues: { status: 'pending', total_amount: 0 },
  });

  // Danh mục tàu/loại tàu giữ trong store dùng chung: chỉ nạp khi còn rỗng (không
  // tải lại mỗi lần mở trang). Danh sách đơn do `usePagedQuery` tự nạp theo trang.
  useEffect(() => {
    if (vessels.length === 0) {
      void fetchVessels();
    }
    if (vesselTypes.length === 0) {
      void fetchVesselTypes();
    }
  }, [vessels.length, vesselTypes.length, fetchVessels, fetchVesselTypes]);

  // Tám bộ lọc `/orders/` có tham số ⇒ server lọc, client không lọc lại.
  const orderFilters = useMemo<OrderFilters>(
    () => ({
      q: orderQ.trim() || undefined,
      status: orderStatusFilter || undefined,
      vesselId: orderShipIdFilter || undefined,
      vesselTypeId: orderVesselTypeFilter || undefined,
      dateFrom: orderDateFrom || undefined,
      dateTo: orderDateTo || undefined,
      minTotal: orderMinAmt.trim() || undefined,
      maxTotal: orderMaxAmt.trim() || undefined,
    }),
    [
      orderQ,
      orderStatusFilter,
      orderShipIdFilter,
      orderVesselTypeFilter,
      orderDateFrom,
      orderDateTo,
      orderMinAmt,
      orderMaxAmt,
    ],
  );

  const {
    items: orders,
    total: ordersTotal,
    page: ordersPage,
    pageSize: ordersPageSize,
    isLoading: ordersLoading,
    error: ordersError,
    setPage: setOrdersPage,
    setPageSize: setOrdersPageSize,
    setFilters: setOrderFilters,
    setSort: setOrderSort,
    reload: reloadOrders,
  } = usePagedQuery<OrderRead, OrderFilters, OrderSort>({
    fetcher: fetchOrdersPage,
    filters: orderFilters,
  });

  // Đẩy nội dung bộ lọc xuống hook; object đã memo hoá nên hiệu ứng chỉ chạy khi
  // bộ lọc THỰC SỰ đổi. Bỏ qua lần chạy đầu vì hook đã KHỞI TẠO bằng chính
  // `orderFilters` (đẩy lại đúng object đó chỉ thêm một request thừa lúc mở trang).
  const pushedOrderFiltersRef = useRef(orderFilters);
  useEffect(() => {
    if (pushedOrderFiltersRef.current === orderFilters) {
      return;
    }
    pushedOrderFiltersRef.current = orderFilters;
    setOrderFilters(orderFilters);
  }, [orderFilters, setOrderFilters]);

  // Sau mỗi thao tác ghi: nạp lại ĐÚNG trang/bộ lọc đang xem.
  const reloadOrderList = useCallback(() => {
    reloadOrders();
  }, [reloadOrders]);

  const orderFilterCount =
    (orderQ.trim() ? 1 : 0) +
    (orderStatusFilter ? 1 : 0) +
    (orderShipIdFilter ? 1 : 0) +
    (orderVesselTypeFilter ? 1 : 0) +
    (orderDateFrom ? 1 : 0) +
    (orderDateTo ? 1 : 0) +
    (orderMinAmt.trim() ? 1 : 0) +
    (orderMaxAmt.trim() ? 1 : 0);

  const resetOrderFilters = () => {
    setOrderQ('');
    setOrderStatusFilter('');
    setOrderShipIdFilter('');
    setOrderVesselTypeFilter('');
    setOrderDateFrom('');
    setOrderDateTo('');
    setOrderMinAmt('');
    setOrderMaxAmt('');
  };

  const onSubmit = async (data: OrderCreate) => {
    try {
      if (editingId) {
        await updateOrder(editingId, data as OrderUpdate);
      } else {
        await createOrder(data);
      }
      setIsModalOpen(false);
      form.reset();
      setEditingId(null);
      reloadOrderList();
    } catch (err) {
      console.error(err);
    }
  };

  const handleEdit = (order: OrderRead) => {
    setEditingId(String(order.id));
    form.reset({
      vessel_id: order.vessel_id != null ? String(order.vessel_id) : '',
      cargo_details: order.cargo_details,
      total_amount: Number(order.total_amount ?? 0),
      status: order.status,
    });
    setIsModalOpen(true);
  };

  const handleDelete = async (id: string) => {
    if (!window.confirm('Xác nhận xóa đơn hàng này?')) {
      return;
    }
    await deleteOrder(id);
    reloadOrderList();
  };

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <OrdersListSection
        orderQ={orderQ}
        setOrderQ={setOrderQ}
        orderStatusFilter={orderStatusFilter}
        setOrderStatusFilter={setOrderStatusFilter}
        orderShipIdFilter={orderShipIdFilter}
        setOrderShipIdFilter={setOrderShipIdFilter}
        orderVesselTypeFilter={orderVesselTypeFilter}
        setOrderVesselTypeFilter={setOrderVesselTypeFilter}
        orderDateFrom={orderDateFrom}
        setOrderDateFrom={setOrderDateFrom}
        orderDateTo={orderDateTo}
        setOrderDateTo={setOrderDateTo}
        orderMinAmt={orderMinAmt}
        setOrderMinAmt={setOrderMinAmt}
        orderMaxAmt={orderMaxAmt}
        setOrderMaxAmt={setOrderMaxAmt}
        resetOrderFilters={resetOrderFilters}
        orderFilterCount={orderFilterCount}
        onOpenCreate={() => {
          setEditingId(null);
          form.reset({ status: 'pending', total_amount: 0 });
          setIsModalOpen(true);
        }}
        orders={orders}
        vessels={vessels}
        vesselTypes={vesselTypes}
        isLoading={ordersLoading}
        error={ordersError}
        page={ordersPage}
        pageSize={ordersPageSize}
        total={ordersTotal}
        onPageChange={setOrdersPage}
        onPageSizeChange={setOrdersPageSize}
        onSortChange={setOrderSort}
        onEdit={handleEdit}
        onDelete={handleDelete}
      />

      <OrderFormModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        form={form}
        onSubmit={onSubmit}
        editingId={editingId}
        vessels={vessels}
        isLoading={isLoading}
      />
    </div>
  );
};
