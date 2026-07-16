import { httpClient } from '../../../services/httpClient';
import type { PortLogRead } from '../../../types/api.types';

export type OutsideHoursSummaryRow = {
  ship_id: string;
  /** Ngày VN dạng 'YYYY-MM-DD' */
  date: string;
  /** Số lượt neo ngoài khung giờ cho phép trong ngày đó */
  count: number;
};

export const statisticsApi = {
  getPortLogs: async (skip: number = 0, limit: number = 100, shipId?: string, logDate?: string): Promise<PortLogRead[]> => {
    const params = new URLSearchParams({ skip: skip.toString(), limit: limit.toString() });
    if (shipId) params.append('ship_id', shipId);
    if (logDate) params.append('log_date', logDate);
    return httpClient.get<PortLogRead[]>(`/port-logs/?${params.toString()}`);
  },
  getOutsideHoursSummary: async (
    dateFrom?: string,
    dateTo?: string,
    shipId?: string,
  ): Promise<OutsideHoursSummaryRow[]> => {
    const params = new URLSearchParams();
    if (dateFrom) params.append('date_from', dateFrom);
    if (dateTo) params.append('date_to', dateTo);
    if (shipId) params.append('ship_id', shipId);
    const qs = params.toString();
    return httpClient.get<OutsideHoursSummaryRow[]>(
      `/port-logs/outside-hours-summary${qs ? `?${qs}` : ''}`,
    );
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
