export function getDetectionMediaOrigin(): string {
  const apiBase = (import.meta.env.VITE_API_BASE_URL || '').trim();
  const proxyTarget = (import.meta.env.VITE_API_PROXY_TARGET || '').trim();

  if (/^https?:\/\//i.test(apiBase)) {
    try {
      return new URL(apiBase).origin;
    } catch {
      // ignore invalid env and continue fallback chain
    }
  }

  if (proxyTarget && !/^https?:\/\//i.test(apiBase)) {
    try {
      return new URL(proxyTarget).origin;
    } catch {
      // ignore invalid env and continue fallback chain
    }
  }

  if (typeof window !== 'undefined' && window.location?.origin) {
    return window.location.origin;
  }
  return '';
}

export function resolveDetectionMediaUrl(filePath: string): string | null {
  const raw = (filePath || '').trim();
  if (!raw) {
    return null;
  }
  if (raw.startsWith('http://') || raw.startsWith('https://')) {
    return raw;
  }
  if (raw.startsWith('minio://')) {
    return null;
  }
  const normalized = raw.replaceAll('\\', '/').replace(/^\.?\//, '');
  if (!normalized.startsWith('runs/')) {
    return null;
  }
  const relative = `/${normalized}`;
  const origin = getDetectionMediaOrigin();
  return origin ? `${origin}${relative}` : relative;
}
