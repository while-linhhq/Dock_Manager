import { create } from 'zustand';
import type { InvoiceRead } from '../../../types/api.types';
import {
  discountApprovalApi,
  type DiscountRequestStatus,
} from '../services/discountApprovalApi';

interface DiscountApprovalState {
  requests: InvoiceRead[];
  statusTab: DiscountRequestStatus;
  isLoading: boolean;
  error: string | null;
  setStatusTab: (tab: DiscountRequestStatus) => void;
  fetchRequests: () => Promise<void>;
  approveRequest: (id: string | number) => Promise<void>;
  rejectRequest: (id: string | number, reason?: string) => Promise<void>;
}

export const useDiscountApprovalStore = create<DiscountApprovalState>((set, get) => ({
  requests: [],
  statusTab: 'pending',
  isLoading: false,
  error: null,

  setStatusTab: (statusTab) => {
    set({ statusTab });
    void get().fetchRequests();
  },

  fetchRequests: async () => {
    set({ isLoading: true, error: null });
    try {
      const requests = await discountApprovalApi.listRequests(get().statusTab);
      set({ requests, isLoading: false });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to fetch discount requests';
      set({ error: message, isLoading: false });
    }
  },

  approveRequest: async (id) => {
    set({ error: null });
    try {
      await discountApprovalApi.approve(id);
      await get().fetchRequests();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to approve discount';
      set({ error: message });
      throw err;
    }
  },

  rejectRequest: async (id, reason) => {
    set({ error: null });
    try {
      await discountApprovalApi.reject(id, reason);
      await get().fetchRequests();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to reject discount';
      set({ error: message });
      throw err;
    }
  },
}));
