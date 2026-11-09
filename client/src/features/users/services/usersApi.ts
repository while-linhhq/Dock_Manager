import { httpClient } from '../../../services/httpClient';
import type { UserRead, RoleRead } from '../../../types/api.types';

export type UserCreate = {
  username: string;
  email: string;
  password: string;
  full_name: string;
  role_id: number;
  is_active?: boolean;
}

export type UserUpdate = {
  email?: string;
  full_name?: string;
  role_id?: number;
  phone?: string;
  is_active?: boolean;
}

export type RolePermissions = {
  all?: boolean;
  menus?: string[];
}

export type RoleCreate = {
  role_name: string;
  description?: string;
  permissions?: RolePermissions;
}

export type RoleUpdate = {
  role_name?: string;
  description?: string;
  permissions?: RolePermissions;
}

export const usersApi = {
  /** Danh mục người dùng — mặc định xin tới trần danh mục 1000 (server: 100). */
  getUsers: async (skip: number = 0, limit: number = 1000): Promise<UserRead[]> => {
    return httpClient.get<UserRead[]>(`/users/?skip=${skip}&limit=${limit}`);
  },
  getUser: async (id: string): Promise<UserRead> => {
    return httpClient.get<UserRead>(`/users/${id}`);
  },
  createUser: async (data: UserCreate): Promise<UserRead> => {
    return httpClient.post<UserRead>('/users/', data);
  },
  updateUser: async (id: string, data: UserUpdate): Promise<UserRead> => {
    return httpClient.put<UserRead>(`/users/${id}`, data);
  },
  deleteUser: async (id: string): Promise<void> => {
    return httpClient.delete(`/users/${id}`);
  },
  /** Danh mục vai trò — xin tường minh tới trần danh mục 1000. */
  getRoles: async (): Promise<RoleRead[]> => {
    return httpClient.get<RoleRead[]>('/roles/?skip=0&limit=1000');
  },
  createRole: async (data: RoleCreate): Promise<RoleRead> => {
    return httpClient.post<RoleRead>('/roles/', data);
  },
  updateRole: async (id: string, data: RoleUpdate): Promise<RoleRead> => {
    return httpClient.put<RoleRead>(`/roles/${id}`, data);
  },
  deleteRole: async (id: string): Promise<void> => {
    return httpClient.delete(`/roles/${id}`);
  },
  updateMe: async (data: {
    email?: string;
    full_name?: string;
    phone?: string;
    password?: string;
  }): Promise<UserRead> => {
    return httpClient.put<UserRead>('/users/me', data);
  },
};
