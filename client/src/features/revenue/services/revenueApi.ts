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
  fee_name: string;
  vessel_type_id?: number | null;
  base_fee: number;
  unit?: string | null;
  is_active?: boolean;
  effective_from?: string | null;
  effective_to?: string | null;
}

export type FeeConfigUpdatePayload = {
  fee_name?: string;
  base_fee?: number;
  unit?: string | null;
  is_active?: boolean;
  effective_from?: string | null;
  effective_to?: string | null;
}

export type InvoiceListParams = {
  skip?: number;
  limit?: number;
  /** Exact backend status e.g. PAID */
  paymentStatus?: string;
  /** Chờ thanh toán: mọi trạng thái trừ PAID */
  awaitingPayment?: boolean;
  /** Hóa đơn đã xóa mềm */
  deletedOnly?: boolean;
  /** Chỉ HĐ tự động (AI) */
  creationSource?: string;
  /** Ẩn một nguồn (dùng AI để tab hóa đơn thường) */
  excludeCreationSource?: string;
};

export const revenueApi = {
  getInvoices: async (params: InvoiceListParams = {}): Promise<InvoiceRead[]> => {
    const q = new URLSearchParams({
      skip: String(params.skip ?? 0),
      limit: String(params.limit ?? 100),
    });
    if (params.deletedOnly) {
      q.set('deleted_only', 'true');
    } else if (params.awaitingPayment) {
      q.set('awaiting_payment', 'true');
    } else if (params.paymentStatus) {
      q.set('payment_status', params.paymentStatus);
    }
    if (params.creationSource) {
      q.set('creation_source', params.creationSource);
    } else if (params.excludeCreationSource) {
      q.set('exclude_creation_source', params.excludeCreationSource);
    }
    return httpClient.get<InvoiceRead[]>(`/invoices/?${q.toString()}`);
  },
  getInvoice: async (id: string): Promise<InvoiceRead> => {
    return httpClient.get<InvoiceRead>(`/invoices/${id}`);
  },
  createInvoice: async (data: InvoiceCreate): Promise<InvoiceRead> => {
    return httpClient.post<InvoiceRead>('/invoices/', {
      order_id: Number(data.order_id),
      items: data.items.map((it) => ({
        description: it.description,
        quantity: it.quantity,
        unit_price: it.unit_price,
      })),
    });
  },
  deleteInvoice: async (id: string | number): Promise<void> => {
    await httpClient.delete(`/invoices/${id}`);
  },
  getPayments: async (invoiceId: string): Promise<PaymentRead[]> => {
    return httpClient.get<PaymentRead[]>(`/invoices/${invoiceId}/payments`);
  },
  createPayment: async (invoiceId: string | number, data: PaymentCreate): Promise<PaymentRead> => {
    return httpClient.post<PaymentRead>(`/invoices/${invoiceId}/payments`, {
      invoice_id: Number(invoiceId),
      amount: data.amount,
      payment_method: data.payment_method,
      payment_reference: data.reference_number,
      notes: data.notes,
    });
  },
  getFeeConfigs: async (activeOnly: boolean = false): Promise<FeeConfigRead[]> => {
    return httpClient.get<FeeConfigRead[]>(`/fee-configs/?active_only=${activeOnly}`);
  },
  createFeeConfig: async (data: FeeConfigCreate): Promise<FeeConfigRead> => {
    return httpClient.post<FeeConfigRead>('/fee-configs/', data);
  },
  updateFeeConfig: async (
    id: string | number,
    data: FeeConfigUpdatePayload
  ): Promise<FeeConfigRead> => {
    return httpClient.put<FeeConfigRead>(`/fee-configs/${id}`, data);
  },
  deleteFeeConfig: async (id: string | number): Promise<void> => {
    await httpClient.delete(`/fee-configs/${id}`);
  },
};
