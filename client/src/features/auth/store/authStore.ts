import { create } from 'zustand';
import type { UserRead } from '../../../types/api.types';
import { authApi } from '../services/authApi';
import { authStorage } from '../../../services/authStorage';

interface AuthState {
  user: UserRead | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  checkAuth: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: !!authStorage.getToken(),
  isLoading: false,
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
      set({ user, isAuthenticated: true, isLoading: false });
    } catch (err: any) {
      set({ error: err.message || 'Login failed', isLoading: false });
      throw err;
    }
  },
  logout: () => {
    authStorage.removeToken();
    set({ user: null, isAuthenticated: false });
  },
  checkAuth: async () => {
    const token = authStorage.getToken();
    if (!token) {
      set({ isAuthenticated: false, user: null });
      return;
    }

    set({ isLoading: true });
    try {
      const user = await authApi.getMe();
      set({ user, isAuthenticated: true, isLoading: false });
    } catch (err) {
      authStorage.removeToken();
      set({ user: null, isAuthenticated: false, isLoading: false });
    }
  },
}));
