/**
 * Turn API-relative asset paths (e.g. /api/v1/.../preview) into a browser-loadable URL.
 * When VITE_API_BASE_URL is absolute, prefix with that host so <img src> works outside Vite proxy.
 */
export function resolveApiAssetUrl(path: string | null | undefined): string | undefined {
  const trimmed = String(path ?? '').trim();
  if (!trimmed) {
    return undefined;
  }
  if (/^https?:\/\//i.test(trimmed)) {
    return trimmed;
  }

  const apiBase = (import.meta.env.VITE_API_BASE_URL || '').trim();
  if (/^https?:\/\//i.test(apiBase)) {
    try {
      const { origin } = new URL(apiBase);
      return `${origin}${trimmed.startsWith('/') ? trimmed : `/${trimmed}`}`;
    } catch {
      return trimmed;
    }
  }

  return trimmed.startsWith('/') ? trimmed : `/${trimmed}`;
}
