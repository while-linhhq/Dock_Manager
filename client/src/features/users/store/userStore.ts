import { create } from 'zustand';
import type { UserRead, RoleRead } from '../../../types/api.types';
import { usersApi } from '../services/usersApi';
import type { RoleCreate, RoleUpdate } from '../services/usersApi';

interface UserState {
  users: UserRead[];
  roles: RoleRead[];
  isLoading: boolean;
  error: string | null;
  fetchUsers: (skip?: number, limit?: number) => Promise<void>;
  fetchRoles: () => Promise<void>;
  upsertUser: (id: string | null, data: any) => Promise<void>;
  deleteUser: (id: string) => Promise<void>;
  createRole: (data: RoleCreate) => Promise<void>;
  upsertRole: (id: string | null, data: RoleCreate | RoleUpdate) => Promise<void>;
  deleteRole: (id: string) => Promise<void>;
}

export const useUserStore = create<UserState>((set, get) => ({
  users: [],
  roles: [],
  isLoading: false,
  error: null,
  fetchUsers: async (skip, limit) => {
    set({ isLoading: true, error: null });
    try {
      const users = await usersApi.getUsers(skip, limit);
      set({ users, isLoading: false });
    } catch (err: any) {
      set({ error: err.message || 'Failed to fetch users', isLoading: false });
    }
  },
  fetchRoles: async () => {
    set({ isLoading: true, error: null });
    try {
      const roles = await usersApi.getRoles();
      set({ roles, isLoading: false });
    } catch (err: any) {
      set({ error: err.message || 'Failed to fetch roles', isLoading: false });
    }
  },
  upsertUser: async (id, data) => {
    set({ isLoading: true, error: null });
    try {
      if (id) {
        await usersApi.updateUser(id, data);
      } else {
        await usersApi.createUser(data);
      }
      await get().fetchUsers();
    } catch (err: any) {
      set({ error: err.message || 'Failed to save user', isLoading: false });
      throw err;
    }
  },
  deleteUser: async (id) => {
    set({ isLoading: true, error: null });
    try {
      await usersApi.deleteUser(id);
      await get().fetchUsers();
    } catch (err: any) {
      set({ error: err.message || 'Failed to delete user', isLoading: false });
      throw err;
    }
  },
  createRole: async (data) => {
    set({ isLoading: true, error: null });
    try {
      await usersApi.createRole(data);
      await get().fetchRoles();
    } catch (err: any) {
      set({ error: err.message || 'Failed to create role', isLoading: false });
      throw err;
    }
  },
  upsertRole: async (id, data) => {
    set({ isLoading: true, error: null });
    try {
      if (id) {
        await usersApi.updateRole(id, data);
      } else {
        await usersApi.createRole(data as RoleCreate);
      }
      await get().fetchRoles();
    } catch (err: any) {
      set({ error: err.message || 'Failed to save role', isLoading: false });
      throw err;
    }
  },
  deleteRole: async (id) => {
    set({ isLoading: true, error: null });
    try {
      await usersApi.deleteRole(id);
      await get().fetchRoles();
    } catch (err: any) {
      set({ error: err.message || 'Failed to delete role', isLoading: false });
      throw err;
    }
  },
}));
