import { create } from 'zustand';
import { licenseApi } from '../services/licenseApi';
import type { LicenseStatusRead } from '../types';

interface LicenseState {
  status: LicenseStatusRead | null;
  isLoading: boolean;
  error: string | null;
  /** Tải trạng thái license; nuốt lỗi vào `error` để app shell không crash. */
  fetchStatus: () => Promise<void>;
  /** Kích hoạt key; ném lỗi để màn hình kích hoạt hiển thị thông báo. */
  activate: (key: string) => Promise<void>;
  /** Verify lại với Keygate; ném lỗi để nơi gọi chủ động xử lý. */
  refresh: () => Promise<void>;
}

const errorMessage = (err: unknown, fallback: string): string =>
  err instanceof Error && err.message ? err.message : fallback;

export const useLicenseStore = create<LicenseState>((set) => ({
  status: null,
  isLoading: false,
  error: null,

  fetchStatus: async () => {
    set({ isLoading: true, error: null });
    try {
      const status = await licenseApi.getStatus();
      set({ status, isLoading: false });
    } catch (err: unknown) {
      // Không ném lỗi: shell vẫn render bình thường (chế độ cảnh báo).
      set({
        error: errorMessage(err, 'Không tải được trạng thái license'),
        isLoading: false,
      });
    }
  },

  activate: async (key) => {
    set({ isLoading: true, error: null });
    try {
      const status = await licenseApi.activate({ license_key: key });
      set({ status, isLoading: false });
    } catch (err: unknown) {
      set({
        error: errorMessage(err, 'Kích hoạt license thất bại'),
        isLoading: false,
      });
      throw err;
    }
  },

  refresh: async () => {
    set({ isLoading: true, error: null });
    try {
      const status = await licenseApi.refresh();
      set({ status, isLoading: false });
    } catch (err: unknown) {
      set({
        error: errorMessage(err, 'Không làm mới được trạng thái license'),
        isLoading: false,
      });
      throw err;
    }
  },
}));
