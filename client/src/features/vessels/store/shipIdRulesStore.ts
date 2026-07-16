import { create } from 'zustand';
import { shipIdRulesApi } from '../services/shipIdRulesApi';
import type {
  BlacklistCreate,
  BlacklistRead,
  ConvertMapCreate,
  ConvertMapRead,
  ConvertMapUpdate,
  PatternCreate,
  PatternRead,
  PatternUpdate,
  PrefixConvertCreate,
  PrefixConvertRead,
  PrefixConvertUpdate,
} from '../types/ship-id-rules.types';

interface ShipIdRulesState {
  patterns: PatternRead[];
  blacklist: BlacklistRead[];
  convertMap: ConvertMapRead[];
  prefixConvert: PrefixConvertRead[];
  isLoading: boolean;
  error: string | null;

  fetchAll: () => Promise<void>;

  createPattern: (data: PatternCreate) => Promise<void>;
  updatePattern: (id: number, data: PatternUpdate) => Promise<void>;
  deletePattern: (id: number) => Promise<void>;

  createBlacklist: (data: BlacklistCreate) => Promise<void>;
  deleteBlacklist: (id: number) => Promise<void>;

  createConvertMap: (data: ConvertMapCreate) => Promise<void>;
  updateConvertMap: (id: number, data: ConvertMapUpdate) => Promise<void>;
  deleteConvertMap: (id: number) => Promise<void>;

  createPrefixConvert: (data: PrefixConvertCreate) => Promise<void>;
  updatePrefixConvert: (id: number, data: PrefixConvertUpdate) => Promise<void>;
  deletePrefixConvert: (id: number) => Promise<void>;

  forceReload: () => Promise<boolean>;
}

export const useShipIdRulesStore = create<ShipIdRulesState>((set) => ({
  patterns: [],
  blacklist: [],
  convertMap: [],
  prefixConvert: [],
  isLoading: false,
  error: null,

  fetchAll: async () => {
    set({ isLoading: true, error: null });
    try {
      const [patterns, blacklist, convertMap, prefixConvert] = await Promise.all([
        shipIdRulesApi.getPatterns(),
        shipIdRulesApi.getBlacklist(),
        shipIdRulesApi.getConvertMap(),
        shipIdRulesApi.getPrefixConvert(),
      ]);
      set({ patterns, blacklist, convertMap, prefixConvert, isLoading: false });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load rules';
      set({ error: message, isLoading: false });
    }
  },

  createPattern: async (data) => {
    const created = await shipIdRulesApi.createPattern(data);
    set((s) => ({ patterns: [...s.patterns, created] }));
  },

  updatePattern: async (id, data) => {
    const updated = await shipIdRulesApi.updatePattern(id, data);
    set((s) => ({ patterns: s.patterns.map((p) => (p.id === id ? updated : p)) }));
  },

  deletePattern: async (id) => {
    await shipIdRulesApi.deletePattern(id);
    set((s) => ({ patterns: s.patterns.filter((p) => p.id !== id) }));
  },

  createBlacklist: async (data) => {
    const created = await shipIdRulesApi.createBlacklist(data);
    set((s) => ({ blacklist: [created, ...s.blacklist] }));
  },

  deleteBlacklist: async (id) => {
    await shipIdRulesApi.deleteBlacklist(id);
    set((s) => ({ blacklist: s.blacklist.filter((b) => b.id !== id) }));
  },

  createConvertMap: async (data) => {
    const created = await shipIdRulesApi.createConvertMap(data);
    set((s) => ({ convertMap: [created, ...s.convertMap] }));
  },

  updateConvertMap: async (id, data) => {
    const updated = await shipIdRulesApi.updateConvertMap(id, data);
    set((s) => ({ convertMap: s.convertMap.map((c) => (c.id === id ? updated : c)) }));
  },

  deleteConvertMap: async (id) => {
    await shipIdRulesApi.deleteConvertMap(id);
    set((s) => ({ convertMap: s.convertMap.filter((c) => c.id !== id) }));
  },

  createPrefixConvert: async (data) => {
    const created = await shipIdRulesApi.createPrefixConvert(data);
    set((s) => ({ prefixConvert: [created, ...s.prefixConvert] }));
  },

  updatePrefixConvert: async (id, data) => {
    const updated = await shipIdRulesApi.updatePrefixConvert(id, data);
    set((s) => ({ prefixConvert: s.prefixConvert.map((p) => (p.id === id ? updated : p)) }));
  },

  deletePrefixConvert: async (id) => {
    await shipIdRulesApi.deletePrefixConvert(id);
    set((s) => ({ prefixConvert: s.prefixConvert.filter((p) => p.id !== id) }));
  },

  forceReload: async () => {
    const result = await shipIdRulesApi.reload();
    return result.reloaded;
  },
}));
