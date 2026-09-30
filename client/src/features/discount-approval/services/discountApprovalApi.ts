import { httpClient } from '../../../services/httpClient';
import type { InvoiceRead } from '../../../types/api.types';

export type DiscountRequestStatus = 'pending' | 'approved' | 'rejected';

export const discountApprovalApi = {
  /**
   * Trang duyệt giảm giá KHÔNG phân trang (endpoint không có `sort` nên chưa
   * chuyển sắp xếp lên server được) — chỉ nâng `limit` lên đúng trần 200 của
   * `resolve_page` để không bỏ sót yêu cầu khi có hơn 100 bản ghi.
   */
  listRequests: async (
    status: DiscountRequestStatus,
    skip = 0,
    limit = 200,
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
