import { authStorage } from './authStorage';
import { getJwtExpMs } from './jwt';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';
const REFRESH_SKEW_MS = 2 * 60 * 1000; // refresh 2 minutes before exp

export class ApiError extends Error {
  status: number;
  data?: unknown;

  constructor(status: number, message: string, data?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  if (refreshPromise) {
    return refreshPromise;
  }
  refreshPromise = (async () => {
    const token = authStorage.getToken();
    if (!token) {
      return null;
    }
    const resp = await fetch(`${BASE_URL}/auth/refresh`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });
    if (!resp.ok) {
      return null;
    }
    const data = (await resp.json()) as { access_token?: string };
    const next = typeof data.access_token === 'string' ? data.access_token : null;
    if (next) {
      authStorage.setToken(next);
    }
    return next;
  })()
    .catch(() => null)
    .finally(() => {
      refreshPromise = null;
    });

  return refreshPromise;
}

async function maybeProactiveRefresh(): Promise<void> {
  const token = authStorage.getToken();
  if (!token) {
    return;
  }
  const expMs = getJwtExpMs(token);
  if (expMs == null) {
    return;
  }
  if (Date.now() >= expMs - REFRESH_SKEW_MS) {
    await refreshAccessToken();
  }
}

async function request<T>(endpoint: string, options: RequestInit = {}, retry = true): Promise<T> {
  await maybeProactiveRefresh();
  const token = authStorage.getToken();
  const headers = new Headers(options.headers);

  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  if (options.body && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(`${BASE_URL}${endpoint}`, {
    ...options,
    headers,
  });

  if (response.status === 401) {
    if (retry) {
      const refreshed = await refreshAccessToken();
      if (refreshed) {
        return request<T>(endpoint, options, false);
      }
    }
    authStorage.removeToken();
    window.location.href = '/login';
    throw new ApiError(401, 'Unauthorized');
  }

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new ApiError(response.status, errorData.detail || 'An error occurred', errorData);
  }

  if (response.status === 204) {
    return {} as T;
  }

  return response.json();
}

export const httpClient = {
  get: <T>(url: string, options?: RequestInit) => request<T>(url, { ...options, method: 'GET' }),
  post: <T>(url: string, body?: any, options?: RequestInit) =>
    request<T>(url, {
      ...options,
      method: 'POST',
      body: body instanceof FormData ? body : JSON.stringify(body),
    }),
  put: <T>(url: string, body?: any, options?: RequestInit) =>
    request<T>(url, {
      ...options,
      method: 'PUT',
      body: body instanceof FormData ? body : JSON.stringify(body),
    }),
  patch: <T>(url: string, body?: any, options?: RequestInit) =>
    request<T>(url, {
      ...options,
      method: 'PATCH',
      body: body instanceof FormData ? body : JSON.stringify(body),
    }),
  delete: <T>(url: string, options?: RequestInit) => request<T>(url, { ...options, method: 'DELETE' }),
};
