import { create } from 'zustand';
import type { InvoiceRead, FeeConfigRead } from '../../../types/api.types';
import { revenueApi } from '../services/revenueApi';
import type { InvoiceCreate, PaymentCreate, FeeConfigCreate } from '../services/revenueApi';

interface RevenueState {
  invoices: InvoiceRead[];
  feeConfigs: FeeConfigRead[];
  isLoading: boolean;
  error: string | null;
  fetchInvoices: (skip?: number, limit?: number, status?: string) => Promise<void>;
  fetchFeeConfigs: (activeOnly?: boolean) => Promise<void>;
  createInvoice: (data: InvoiceCreate) => Promise<void>;
  recordPayment: (invoiceId: string, data: PaymentCreate) => Promise<void>;
  upsertFeeConfig: (id: string | null, data: FeeConfigCreate) => Promise<void>;
}

export const useRevenueStore = create<RevenueState>((set, get) => ({
  invoices: [],
  feeConfigs: [],
  isLoading: false,
  error: null,
  fetchInvoices: async (skip, limit, status) => {
    set({ isLoading: true, error: null });
    try {
      const invoices = await revenueApi.getInvoices(skip, limit, status);
      set({ invoices, isLoading: false });
    } catch (err: any) {
      set({ error: err.message || 'Failed to fetch invoices', isLoading: false });
    }
  },
  fetchFeeConfigs: async (activeOnly) => {
    set({ isLoading: true, error: null });
    try {
      const feeConfigs = await revenueApi.getFeeConfigs(activeOnly);
      set({ feeConfigs, isLoading: false });
    } catch (err: any) {
      set({ error: err.message || 'Failed to fetch fee configs', isLoading: false });
    }
  },
  createInvoice: async (data) => {
    set({ isLoading: true, error: null });
    try {
      await revenueApi.createInvoice(data);
      await get().fetchInvoices();
    } catch (err: any) {
      set({ error: err.message || 'Failed to create invoice', isLoading: false });
      throw err;
    }
  },
  recordPayment: async (invoiceId, data) => {
    set({ isLoading: true, error: null });
    try {
      await revenueApi.createPayment(invoiceId, data);
      await get().fetchInvoices();
    } catch (err: any) {
      set({ error: err.message || 'Failed to record payment', isLoading: false });
      throw err;
    }
  },
  upsertFeeConfig: async (id, data) => {
    set({ isLoading: true, error: null });
    try {
      if (id) {
        await revenueApi.updateFeeConfig(id, data);
      } else {
        await revenueApi.createFeeConfig(data);
      }
      await get().fetchFeeConfigs();
    } catch (err: any) {
      set({ error: err.message || 'Failed to save fee config', isLoading: false });
      throw err;
    }
  },
}));
