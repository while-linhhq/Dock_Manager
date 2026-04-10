import { httpClient } from '../../../services/httpClient';
import type { InvoiceRead, FeeConfigRead, PaymentRead } from '../../../types/api.types';

export type InvoiceCreate = {
  order_id: string;
  items: Array<{
    description: string;
    quantity: number;
    unit_price: number;
  }>;
}

export type PaymentCreate = {
  amount: number;
  payment_method: string;
  reference_number?: string;
  notes?: string;
}

export type FeeConfigCreate = {
  name: string;
  vessel_type_id: string;
  fee_amount: number;
  is_active?: boolean;
}

export const revenueApi = {
  getInvoices: async (skip: number = 0, limit: number = 100, status?: string): Promise<InvoiceRead[]> => {
    const params = new URLSearchParams({ skip: skip.toString(), limit: limit.toString() });
    if (status) params.append('payment_status', status);
    return httpClient.get<InvoiceRead[]>(`/invoices/?${params.toString()}`);
  },
  getInvoice: async (id: string): Promise<InvoiceRead> => {
    return httpClient.get<InvoiceRead>(`/invoices/${id}`);
  },
  createInvoice: async (data: InvoiceCreate): Promise<InvoiceRead> => {
    return httpClient.post<InvoiceRead>('/invoices/', data);
  },
  getPayments: async (invoiceId: string): Promise<PaymentRead[]> => {
    return httpClient.get<PaymentRead[]>(`/invoices/${invoiceId}/payments`);
  },
  createPayment: async (invoiceId: string, data: PaymentCreate): Promise<PaymentRead> => {
    return httpClient.post<PaymentRead>(`/invoices/${invoiceId}/payments`, data);
  },
  getFeeConfigs: async (activeOnly: boolean = false): Promise<FeeConfigRead[]> => {
    return httpClient.get<FeeConfigRead[]>(`/fee-configs/?active_only=${activeOnly}`);
  },
  createFeeConfig: async (data: FeeConfigCreate): Promise<FeeConfigRead> => {
    return httpClient.post<FeeConfigRead>('/fee-configs/', data);
  },
  updateFeeConfig: async (id: string, data: Partial<FeeConfigCreate>): Promise<FeeConfigRead> => {
    return httpClient.put<FeeConfigRead>(`/fee-configs/${id}`, data);
  },
};
