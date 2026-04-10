import { create } from 'zustand';
import type { AuditLogRead } from '../../../types/api.types';
import { backupApi } from '../services/backupApi';
import type { DetectionMediaRead } from '../services/backupApi';

interface BackupState {
  auditLogs: AuditLogRead[];
  isLoading: boolean;
  error: string | null;
  fetchAuditLogs: (userId?: string, limit?: number) => Promise<void>;
  fetchMedia: (detectionId: string) => Promise<DetectionMediaRead[]>;
}

export const useBackupStore = create<BackupState>((set) => ({
  auditLogs: [],
  isLoading: false,
  error: null,
  fetchAuditLogs: async (userId, limit) => {
    set({ isLoading: true, error: null });
    try {
      const auditLogs = await backupApi.getAuditLogs(userId, limit);
      set({ auditLogs, isLoading: false });
    } catch (err: any) {
      set({ error: err.message || 'Failed to fetch audit logs', isLoading: false });
    }
  },
  fetchMedia: async (detectionId) => {
    try {
      return await backupApi.getDetectionMedia(detectionId);
    } catch (err) {
      return [];
    }
  }
}));
