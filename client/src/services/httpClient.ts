import { authStorage } from './authStorage';
import { getJwtExpMs } from './jwt';
import { buildQuery, parseTotalCount } from './paged';
import type { PagedQueryParams, PagedResult } from './paged';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').trim();
const BASE_URL = import.meta.env.DEV
  ? '/api/v1'
  : (API_BASE_URL || '/api/v1');
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
const inFlightGetRequests = new Map<string, Promise<unknown>>();

/**
 * Payload thô của một request: dữ liệu đã parse + Response gốc.
 * Response được chia sẻ qua bản đồ de-dup nên phải đọc body đúng MỘT lần —
 * headers vẫn đọc được sau khi body đã tiêu thụ (vd `X-Total-Count`).
 */
type ResponsePayload<T> = { data: T; response: Response };

function resolveErrorMessage(errorData: unknown): string {
  if (!errorData || typeof errorData !== 'object') {
    return 'An error occurred';
  }

  const detail = (errorData as { detail?: unknown }).detail;
  if (typeof detail === 'string') {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === 'object' && 'msg' in item) {
          return String((item as { msg: unknown }).msg);
        }
        return String(item);
      })
      .join(', ');
  }
  return 'An error occurred';
}

async function refreshAccessToken(): Promise<string | null> {
  if (refreshPromise) {
    return refreshPromise;
  }
  refreshPromise = (async () => {
    const refreshToken = authStorage.getRefreshToken();
    if (!refreshToken) {
      return null;
    }
    const resp = await fetch(`${BASE_URL}/auth/refresh`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!resp.ok) {
      return null;
    }
    const data = (await resp.json()) as {
      access_token?: string;
      refresh_token?: string;
    };
    const next = typeof data.access_token === 'string' ? data.access_token : null;
    if (next) {
      authStorage.setToken(next);
    }
    if (typeof data.refresh_token === 'string') {
      authStorage.setRefreshToken(data.refresh_token);
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

async function requestResponse<T>(
  endpoint: string,
  options: RequestInit = {},
  retry = true,
): Promise<ResponsePayload<T>> {
  const method = (options.method || 'GET').toUpperCase();
  const isGetRequest = method === 'GET';

  const runRequest = async (): Promise<ResponsePayload<T>> => {
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
          return requestResponse<T>(endpoint, options, false);
        }
      }
      authStorage.clear();
      window.location.href = '/login';
      throw new ApiError(401, 'Unauthorized');
    }

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new ApiError(response.status, resolveErrorMessage(errorData), errorData);
    }

    if (response.status === 204) {
      return { data: {} as T, response };
    }

    const data = (await response.json()) as T;
    return { data, response };
  };

  if (!isGetRequest) {
    return runRequest();
  }

  const token = authStorage.getToken() || '';
  const requestKey = `${method}:${endpoint}:${token}`;
  const pending = inFlightGetRequests.get(requestKey) as Promise<ResponsePayload<T>> | undefined;
  if (pending) {
    return pending;
  }

  const current = runRequest().finally(() => {
    inFlightGetRequests.delete(requestKey);
  });
  inFlightGetRequests.set(requestKey, current);
  return current;
}

async function request<T>(endpoint: string, options: RequestInit = {}, retry = true): Promise<T> {
  const { data } = await requestResponse<T>(endpoint, options, retry);
  return data;
}

async function requestBlob(endpoint: string, options: RequestInit = {}, retry = true): Promise<Response> {
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
        return requestBlob(endpoint, options, false);
      }
    }
    authStorage.clear();
    window.location.href = '/login';
    throw new ApiError(401, 'Unauthorized');
  }

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new ApiError(response.status, resolveErrorMessage(errorData), errorData);
  }

  return response;
}

export const httpClient = {
  get: <T>(url: string, options?: RequestInit) => request<T>(url, { ...options, method: 'GET' }),
  /**
   * GET danh sách phân trang: server trả mảng trần + header `X-Total-Count`.
   * Thiếu/không parse được header ⇒ `total = items.length`.
   */
  getPaged: async <T>(url: string, params?: PagedQueryParams): Promise<PagedResult<T>> => {
    const { data, response } = await requestResponse<T[]>(`${url}${buildQuery(params)}`, {
      method: 'GET',
    });
    const items = Array.isArray(data) ? data : [];
    return {
      items,
      total: parseTotalCount(response.headers.get('x-total-count'), items.length),
    };
  },
  post: <T>(url: string, body?: unknown, options?: RequestInit) =>
    request<T>(url, {
      ...options,
      method: 'POST',
      body: body instanceof FormData ? body : JSON.stringify(body),
    }),
  put: <T>(url: string, body?: unknown, options?: RequestInit) =>
    request<T>(url, {
      ...options,
      method: 'PUT',
      body: body instanceof FormData ? body : JSON.stringify(body),
    }),
  patch: <T>(url: string, body?: unknown, options?: RequestInit) =>
    request<T>(url, {
      ...options,
      method: 'PATCH',
      body: body instanceof FormData ? body : JSON.stringify(body),
    }),
  delete: <T>(url: string, options?: RequestInit) => request<T>(url, { ...options, method: 'DELETE' }),
  downloadBlob: async (url: string, options?: RequestInit) => {
    const response = await requestBlob(url, options);
    return response.blob();
  },
};
