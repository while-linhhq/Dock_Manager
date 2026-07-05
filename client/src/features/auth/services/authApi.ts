import { httpClient } from '../../../services/httpClient';
import type { UserRead } from '../../../types/api.types';

export type LoginResponse = {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export const authApi = {
  login: async (formData: FormData): Promise<LoginResponse> => {
    return httpClient.post<LoginResponse>('/auth/login', formData);
  },
  refresh: async (refreshToken: string): Promise<LoginResponse> => {
    return httpClient.post<LoginResponse>('/auth/refresh', { refresh_token: refreshToken });
  },
  getMe: async (): Promise<UserRead> => {
    return httpClient.get<UserRead>('/users/me');
  },
};
