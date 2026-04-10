import { httpClient } from '../../../services/httpClient';
import type { PortLogRead } from '../../../types/api.types';

export const statisticsApi = {
  getPortLogs: async (skip: number = 0, limit: number = 100, shipId?: string, logDate?: string): Promise<PortLogRead[]> => {
    const params = new URLSearchParams({ skip: skip.toString(), limit: limit.toString() });
    if (shipId) params.append('ship_id', shipId);
    if (logDate) params.append('log_date', logDate);
    return httpClient.get<PortLogRead[]>(`/port-logs/?${params.toString()}`);
  },
  exportExcel: async (logDate?: string, shipId?: string): Promise<Blob> => {
    const params = new URLSearchParams();
    if (logDate) params.append('log_date', logDate);
    if (shipId) params.append('ship_id', shipId);
    
    const response = await fetch(`${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'}/exports/port-logs?${params.toString()}`, {
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('auth_token')}`
      }
    });
    return response.blob();
  }
};
