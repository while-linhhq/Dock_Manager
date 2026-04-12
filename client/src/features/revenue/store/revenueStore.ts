import { create } from 'zustand';
import type { InvoiceRead, FeeConfigRead } from '../../../types/api.types';
import { revenueApi } from '../services/revenueApi';
import type {
  InvoiceCreate,
  PaymentCreate,
  FeeConfigCreate,
  FeeConfigUpdatePayload,
} from '../services/revenueApi';

export type InvoiceSubTab = 'pending' | 'paid' | 'trash';

export type InvoiceListKind = 'standard' | 'ai';

interface RevenueState {
  invoices: InvoiceRead[];
  feeConfigs: FeeConfigRead[];
  invoiceSubTab: InvoiceSubTab;
  /** Tab «Hóa đơn» vs «Hóa đơn tự động» — quyết định filter creation_source */
  invoiceListKind: InvoiceListKind;
  isLoading: boolean;
  error: string | null;
  setInvoiceListKind: (kind: InvoiceListKind) => void;
  setInvoiceSubTab: (tab: InvoiceSubTab) => void;
  fetchInvoices: () => Promise<void>;
  fetchFeeConfigs: (activeOnly?: boolean) => Promise<void>;
  createInvoice: (data: InvoiceCreate) => Promise<void>;
  recordPayment: (invoiceId: string | number, data: PaymentCreate) => Promise<void>;
  deleteInvoice: (id: string | number) => Promise<void>;
  upsertFeeConfig: (id: string | number | null, data: FeeConfigCreate) => Promise<void>;
  deleteFeeConfig: (id: string | number) => Promise<void>;
}

export const useRevenueStore = create<RevenueState>((set, get) => ({
  invoices: [],
  feeConfigs: [],
  invoiceSubTab: 'pending',
  invoiceListKind: 'standard',
  isLoading: false,
  error: null,

  setInvoiceListKind: (invoiceListKind) => {
    set({ invoiceListKind });
  },

  setInvoiceSubTab: (invoiceSubTab) => {
    set({ invoiceSubTab });
    void get().fetchInvoices();
  },

  fetchInvoices: async () => {
    set({ isLoading: true, error: null });
    try {
      const tab = get().invoiceSubTab;
      const kind = get().invoiceListKind;
      const sourceFilter =
        kind === 'ai'
          ? { creationSource: 'AI' as const }
          : { excludeCreationSource: 'AI' as const };
      let invoices: InvoiceRead[];
      if (tab === 'trash') {
        invoices = await revenueApi.getInvoices({ deletedOnly: true, ...sourceFilter });
      } else if (tab === 'paid') {
        invoices = await revenueApi.getInvoices({ paymentStatus: 'PAID', ...sourceFilter });
      } else {
        invoices = await revenueApi.getInvoices({ awaitingPayment: true, ...sourceFilter });
      }
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

  deleteInvoice: async (id) => {
    set({ isLoading: true, error: null });
    try {
      await revenueApi.deleteInvoice(id);
      await get().fetchInvoices();
    } catch (err: any) {
      set({ error: err.message || 'Failed to delete invoice', isLoading: false });
      throw err;
    }
  },

  upsertFeeConfig: async (id, data) => {
    set({ isLoading: true, error: null });
    try {
      if (id != null && id !== '') {
        const patch: FeeConfigUpdatePayload = {
          fee_name: data.fee_name,
          base_fee: data.base_fee,
          is_active: data.is_active,
          unit: data.unit,
          effective_from: data.effective_from,
          effective_to: data.effective_to,
        };
        await revenueApi.updateFeeConfig(id, patch);
      } else {
        await revenueApi.createFeeConfig(data);
      }
      await get().fetchFeeConfigs();
    } catch (err: any) {
      set({ error: err.message || 'Failed to save fee config', isLoading: false });
      throw err;
    }
  },

  deleteFeeConfig: async (id) => {
    set({ isLoading: true, error: null });
    try {
      await revenueApi.deleteFeeConfig(id);
      await get().fetchFeeConfigs();
    } catch (err: any) {
      set({ error: err.message || 'Failed to delete fee config', isLoading: false });
      throw err;
    }
  },
}));
