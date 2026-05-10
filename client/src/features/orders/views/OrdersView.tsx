import React, { useEffect, useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useOrderStore } from '../store/orderStore';
import { useVesselStore } from '../../vessels/store/vesselStore';
import type { OrderCreate, OrderUpdate } from '../services/ordersApi';
import type { OrderRead } from '../../../types/api.types';
import { isoInLocalDateRange, matchesAnyField } from '../../../utils/table-filters';
import { orderSchema } from '../orders-schemas';
import { normOrderStatus } from '../utils/order-status-display';
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

  const { orders, isLoading, fetchOrders, createOrder, updateOrder, deleteOrder } = useOrderStore();
  const { vessels, vesselTypes, fetchVessels, fetchVesselTypes } = useVesselStore();

  const form = useForm<OrderCreate>({
    resolver: zodResolver(orderSchema),
    defaultValues: { status: 'pending', total_amount: 0 },
  });

  useEffect(() => {
    fetchOrders();
    fetchVessels();
    fetchVesselTypes();
  }, [fetchOrders, fetchVessels, fetchVesselTypes]);

  const filteredOrders = useMemo(() => {
    return orders.filter((order) => {
      if (
        !matchesAnyField(
          orderQ,
          String(order.id),
          order.vessel?.ship_id,
          order.vessel?.name,
          order.cargo_details,
        )
      ) {
        return false;
      }
      if (orderStatusFilter) {
        const st = normOrderStatus(String(order.status ?? 'pending'));
        if (st !== orderStatusFilter) {
          return false;
        }
      }
      const matchedVessel = vessels.find((vessel) => String(vessel.id) === String(order.vessel_id ?? ''));
      if (orderShipIdFilter && String(order.vessel_id ?? matchedVessel?.id ?? '') !== orderShipIdFilter) {
        return false;
      }
      if (
        orderVesselTypeFilter &&
        String(matchedVessel?.vessel_type_id ?? '') !== orderVesselTypeFilter
      ) {
        return false;
      }
      if (!isoInLocalDateRange(order.created_at, orderDateFrom, orderDateTo)) {
        return false;
      }
      const amt = Number(order.total_amount ?? 0);
      if (orderMinAmt.trim() && amt < Number(orderMinAmt)) {
        return false;
      }
      if (orderMaxAmt.trim() && amt > Number(orderMaxAmt)) {
        return false;
      }
      return true;
    });
  }, [
    orders,
    orderQ,
    orderStatusFilter,
    orderShipIdFilter,
    orderVesselTypeFilter,
    orderDateFrom,
    orderDateTo,
    orderMinAmt,
    orderMaxAmt,
    vessels,
  ]);

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
        filteredOrders={filteredOrders}
        vessels={vessels}
        vesselTypes={vesselTypes}
        isLoading={isLoading}
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
