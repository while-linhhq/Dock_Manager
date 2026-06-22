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
} from '../types/ship-id-rules.types';

interface ShipIdRulesState {
  patterns: PatternRead[];
  blacklist: BlacklistRead[];
  convertMap: ConvertMapRead[];
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

  forceReload: () => Promise<boolean>;
}

export const useShipIdRulesStore = create<ShipIdRulesState>((set) => ({
  patterns: [],
  blacklist: [],
  convertMap: [],
  isLoading: false,
  error: null,

  fetchAll: async () => {
    set({ isLoading: true, error: null });
    try {
      const [patterns, blacklist, convertMap] = await Promise.all([
        shipIdRulesApi.getPatterns(),
        shipIdRulesApi.getBlacklist(),
        shipIdRulesApi.getConvertMap(),
      ]);
      set({ patterns, blacklist, convertMap, isLoading: false });
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

  forceReload: async () => {
    const result = await shipIdRulesApi.reload();
    return result.reloaded;
  },
}));
