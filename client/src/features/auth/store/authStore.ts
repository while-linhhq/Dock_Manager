import { create } from 'zustand';
import type { UserRead } from '../../../types/api.types';
import { authApi } from '../services/authApi';
import { authStorage } from '../../../services/authStorage';

interface AuthState {
  user: UserRead | null;
  isAuthenticated: boolean;
  /** True sau lần checkAuth đầu (hoặc không có token — không cần chờ). */
  authBootstrapped: boolean;
  isLoading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  checkAuth: () => Promise<void>;
  setUserProfile: (user: UserRead) => void;
}

const initialToken = authStorage.getToken();

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: !!initialToken,
  authBootstrapped: !initialToken,
  isLoading: !!initialToken,
  error: null,
  login: async (email, password) => {
    set({ isLoading: true, error: null });
    try {
      const formData = new FormData();
      formData.append('username', email);
      formData.append('password', password);

      const { access_token } = await authApi.login(formData);
      authStorage.setToken(access_token);

      const user = await authApi.getMe();
      set({ user, isAuthenticated: true, isLoading: false, authBootstrapped: true });
    } catch (err: any) {
      set({ error: err.message || 'Login failed', isLoading: false });
      throw err;
    }
  },
  logout: () => {
    authStorage.removeToken();
    set({ user: null, isAuthenticated: false, authBootstrapped: true, isLoading: false });
  },
  checkAuth: async () => {
    const token = authStorage.getToken();
    if (!token) {
      set({ isAuthenticated: false, user: null, authBootstrapped: true, isLoading: false });
      return;
    }

    set({ isLoading: true });
    try {
      const user = await authApi.getMe();
      set({ user, isAuthenticated: true, isLoading: false, authBootstrapped: true });
    } catch (err) {
      authStorage.removeToken();
      set({
        user: null,
        isAuthenticated: false,
        isLoading: false,
        authBootstrapped: true,
      });
    }
  },
  setUserProfile: (user) => {
    set({ user });
  },
}));
