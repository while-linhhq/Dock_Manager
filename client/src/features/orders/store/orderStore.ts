import { create } from 'zustand';
import type { OrderRead } from '../../../types/api.types';
import { ordersApi } from '../services/ordersApi';
import type { OrderCreate, OrderUpdate } from '../services/ordersApi';

interface OrderState {
  orders: OrderRead[];
  isLoading: boolean;
  error: string | null;
  fetchOrders: (skip?: number, limit?: number, status?: string) => Promise<void>;
  createOrder: (data: OrderCreate) => Promise<void>;
  updateOrder: (id: string, data: OrderUpdate) => Promise<void>;
  updateOrderStatus: (id: string, status: string) => Promise<void>;
  deleteOrder: (id: string) => Promise<void>;
}

export const useOrderStore = create<OrderState>((set, get) => ({
  orders: [],
  isLoading: false,
  error: null,
  fetchOrders: async (skip, limit, status) => {
    set({ isLoading: true, error: null });
    try {
      const orders = await ordersApi.getOrders(skip, limit, status);
      set({ orders, isLoading: false });
    } catch (err: any) {
      set({ error: err.message || 'Failed to fetch orders', isLoading: false });
    }
  },
  createOrder: async (data) => {
    set({ isLoading: true, error: null });
    try {
      await ordersApi.createOrder(data);
      await get().fetchOrders();
    } catch (err: any) {
      set({ error: err.message || 'Failed to create order', isLoading: false });
      throw err;
    }
  },
  updateOrder: async (id, data) => {
    set({ isLoading: true, error: null });
    try {
      await ordersApi.updateOrder(id, data);
      await get().fetchOrders();
    } catch (err: any) {
      set({ error: err.message || 'Failed to update order', isLoading: false });
      throw err;
    }
  },
  updateOrderStatus: async (id, status) => {
    set({ isLoading: true, error: null });
    try {
      await ordersApi.updateStatus(id, status);
      await get().fetchOrders();
    } catch (err: any) {
      set({ error: err.message || 'Failed to update order status', isLoading: false });
      throw err;
    }
  },
  deleteOrder: async (id) => {
    set({ isLoading: true, error: null });
    try {
      await ordersApi.deleteOrder(id);
      await get().fetchOrders();
    } catch (err: any) {
      set({ error: err.message || 'Failed to delete order', isLoading: false });
      throw err;
    }
  },
}));
