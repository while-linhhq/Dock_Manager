import { httpClient } from '../../../services/httpClient';
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

const BASE = '/ship-id-rules';

export const shipIdRulesApi = {
  getPatterns: () => httpClient.get<PatternRead[]>(`${BASE}/patterns`),
  createPattern: (data: PatternCreate) =>
    httpClient.post<PatternRead>(`${BASE}/patterns`, data),
  updatePattern: (id: number, data: PatternUpdate) =>
    httpClient.put<PatternRead>(`${BASE}/patterns/${id}`, data),
  deletePattern: (id: number) => httpClient.delete(`${BASE}/patterns/${id}`),

  getBlacklist: () => httpClient.get<BlacklistRead[]>(`${BASE}/blacklist`),
  createBlacklist: (data: BlacklistCreate) =>
    httpClient.post<BlacklistRead>(`${BASE}/blacklist`, data),
  deleteBlacklist: (id: number) => httpClient.delete(`${BASE}/blacklist/${id}`),

  getConvertMap: () => httpClient.get<ConvertMapRead[]>(`${BASE}/convert-map`),
  createConvertMap: (data: ConvertMapCreate) =>
    httpClient.post<ConvertMapRead>(`${BASE}/convert-map`, data),
  updateConvertMap: (id: number, data: ConvertMapUpdate) =>
    httpClient.put<ConvertMapRead>(`${BASE}/convert-map/${id}`, data),
  deleteConvertMap: (id: number) => httpClient.delete(`${BASE}/convert-map/${id}`),

  reload: () => httpClient.post<{ reloaded: boolean }>(`${BASE}/reload`, {}),
};
