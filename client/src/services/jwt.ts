export function getJwtExpMs(token: string): number | null {
  try {
    const parts = token.split('.');
    if (parts.length < 2) {
      return null;
    }
    const payloadB64 = parts[1];
    const payloadJson = atob(payloadB64.replace(/-/g, '+').replace(/_/g, '/'));
    const payload = JSON.parse(payloadJson) as { exp?: number };
    if (typeof payload.exp !== 'number') {
      return null;
    }
    return payload.exp * 1000;
  } catch {
    return null;
  }
}

