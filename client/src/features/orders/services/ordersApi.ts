import { httpClient } from '../../../services/httpClient';
import type { OrderRead } from '../../../types/api.types';

export type OrderCreate = {
  vessel_id: string;
  cargo_details?: string;
  total_amount: number;
  status?: string;
}

export type OrderUpdate = {
  vessel_id?: string;
  cargo_details?: string;
  total_amount?: number;
  status?: string;
}

export const ordersApi = {
  getOrders: async (skip: number = 0, limit: number = 100, status?: string): Promise<OrderRead[]> => {
    const params = new URLSearchParams({ skip: skip.toString(), limit: limit.toString() });
    if (status) params.append('status', status);
    return httpClient.get<OrderRead[]>(`/orders/?${params.toString()}`);
  },
  getOrder: async (id: string): Promise<OrderRead> => {
    return httpClient.get<OrderRead>(`/orders/${id}`);
  },
  createOrder: async (data: OrderCreate): Promise<OrderRead> => {
    return httpClient.post<OrderRead>('/orders/', data);
  },
  updateOrder: async (id: string, data: OrderUpdate): Promise<OrderRead> => {
    return httpClient.put<OrderRead>(`/orders/${id}`, data);
  },
  updateStatus: async (id: string, status: string): Promise<OrderRead> => {
    return httpClient.patch<OrderRead>(`/orders/${id}/status`, { status });
  },
  deleteOrder: async (id: string): Promise<void> => {
    return httpClient.delete(`/orders/${id}`);
  },
};
