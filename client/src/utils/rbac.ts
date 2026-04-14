import type { UserRead } from '../types/api.types';

export type MenuKey =
  | 'dashboard'
  | 'orders'
  | 'revenue'
  | 'vessels'
  | 'port'
  | 'stats'
  | 'backup'
  | 'users'
  | 'profile';

export const ALL_MENU_KEYS: MenuKey[] = [
  'dashboard',
  'orders',
  'revenue',
  'vessels',
  'port',
  'stats',
  'backup',
  'users',
  'profile',
];

const MENU_ALIAS: Record<MenuKey, string[]> = {
  dashboard: ['dashboard', 'home'],
  orders: ['orders'],
  revenue: ['revenue', 'billing', 'invoices'],
  vessels: ['vessels', 'ships'],
  port: ['port'],
  stats: ['stats', 'statistics'],
  backup: ['backup', 'history'],
  users: ['users', 'rbac', 'roles'],
  profile: ['profile'],
};

function getPermissionObject(user: UserRead | null | undefined): Record<string, unknown> {
  const raw = user?.role?.permissions;
  if (!raw || typeof raw !== 'object') {
    return {};
  }
  return raw as Record<string, unknown>;
}

function normalizedSet(input: unknown): Set<string> {
  if (!Array.isArray(input)) {
    return new Set<string>();
  }
  return new Set(input.map((v) => String(v).trim().toLowerCase()));
}

export function isAdminUser(user: UserRead | null | undefined): boolean {
  const username = String(user?.username ?? '')
    .trim()
    .toLowerCase();
  if (username === 'admin') {
    return true;
  }
  const roleName = String(user?.role?.role_name ?? user?.role?.name ?? '')
    .trim()
    .toLowerCase();
  if (roleName === 'admin') {
    return true;
  }
  const perms = getPermissionObject(user);
  return perms.all === true;
}

export function hasMenuAccess(
  user: UserRead | null | undefined,
  menu: MenuKey,
): boolean {
  if (!user) {
    return false;
  }
  if (isAdminUser(user)) {
    return true;
  }
  const perms = getPermissionObject(user);
  const aliases = MENU_ALIAS[menu];

  const menuAccess = perms.menu_access;
  if (menuAccess && typeof menuAccess === 'object') {
    const map = menuAccess as Record<string, unknown>;
    for (const alias of aliases) {
      if (map[alias] === true) {
        return true;
      }
    }
  }

  const allowedMenus = normalizedSet(perms.allowed_menus ?? perms.menus);
  if (allowedMenus.size > 0) {
    for (const alias of aliases) {
      if (allowedMenus.has(alias)) {
        return true;
      }
    }
    return false;
  }

  // Backward compatibility: granular booleans in permission object.
  for (const alias of aliases) {
    if (perms[alias] === true) {
      return true;
    }
  }

  return false;
}

export function getAccessibleMenus(user: UserRead | null | undefined): MenuKey[] {
  if (!user) {
    return [];
  }
  if (isAdminUser(user)) {
    return ALL_MENU_KEYS;
  }
  return ALL_MENU_KEYS.filter((menu) => hasMenuAccess(user, menu));
}
