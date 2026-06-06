import { httpClient } from '../../../services/httpClient';
import type { InvoiceRead } from '../../../types/api.types';

export type DiscountRequestStatus = 'pending' | 'approved' | 'rejected';

export const discountApprovalApi = {
  listRequests: async (
    status: DiscountRequestStatus,
    skip = 0,
    limit = 100,
  ): Promise<InvoiceRead[]> => {
    const q = new URLSearchParams({
      status,
      skip: String(skip),
      limit: String(limit),
    });
    return httpClient.get<InvoiceRead[]>(`/invoices/discount-requests?${q.toString()}`);
  },
  approve: async (invoiceId: string | number): Promise<InvoiceRead> => {
    return httpClient.post<InvoiceRead>(`/invoices/${invoiceId}/discount/approve`, {});
  },
  reject: async (
    invoiceId: string | number,
    reason?: string,
  ): Promise<InvoiceRead> => {
    return httpClient.post<InvoiceRead>(`/invoices/${invoiceId}/discount/reject`, {
      reason: reason?.trim() || undefined,
    });
  },
};
