import { create } from 'zustand';
import type { AuditLogRead } from '../../../types/api.types';
import { backupApi } from '../services/backupApi';
import type { AuditLogPageRequest, DetectionMediaRead } from '../services/backupApi';

interface BackupState {
  /**
   * Một trang lịch sử hệ thống cho `usePagedQuery`. Trang/bộ lọc/loading do hook
   * giữ nên store không còn sao chép danh sách và cờ loading về đây.
   */
  fetchAuditLogsPage: (
    request: AuditLogPageRequest,
  ) => Promise<{ items: AuditLogRead[]; total: number }>;
  fetchMedia: (detectionId: string) => Promise<DetectionMediaRead[]>;
}

export const useBackupStore = create<BackupState>(() => ({
  fetchAuditLogsPage: async (request) => {
    return backupApi.getAuditLogsPage(request);
  },
  fetchMedia: async (detectionId) => {
    try {
      return await backupApi.getDetectionMedia(detectionId);
    } catch {
      return [];
    }
  },
}));
