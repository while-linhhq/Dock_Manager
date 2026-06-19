/**
 * Cloudflare Worker — Zalo webhook + media fetch proxy (Java User-Agent bypass).
 *
 * Zalo Bot Platform uses User-Agent `Java/1.8.0_192` for webhooks AND sendPhoto URL fetches.
 * Cloudflare often blocks that UA on GET/HEAD (403/1010).
 *
 * Deploy ONE worker with routes:
 *   api-basondock.iotforce.io.vn/api/v1/zalo/webhook*
 *   api-basondock.iotforce.io.vn/api/v1/media/v/*
 *   api-basondock.iotforce.io.vn/api/v1/media/preview/*
 *
 * Variables: ZALO_WEBHOOK_SECRET = same as server .env
 */
export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === 'GET' || request.method === 'HEAD') {
      const zaloMediaMatch = url.pathname.match(
        /^\/api\/v1\/zalo\/webhook\/media\/(v\/[^/]+(?:\.[a-z0-9]+)?|preview\/.*)$/i,
      );
      if (zaloMediaMatch) {
        return proxyMediaOrigin(request, url, `/api/v1/zalo/media/origin/${zaloMediaMatch[1]}`);
      }

      const legacyMediaMatch = url.pathname.match(
        /^\/api\/v1\/media\/(v\/[^/]+(?:\.[a-z0-9]+)?|preview\/.*)$/i,
      );
      if (legacyMediaMatch) {
        return proxyMediaOrigin(request, url, `/api/v1/media/origin/${legacyMediaMatch[1]}`);
      }

      if (url.pathname === '/api/v1/zalo/webhook') {
        return Response.json({
          ok: true,
          message: 'Zalo webhook via Cloudflare Worker',
          forward: '/api/v1/zalo/webhook-origin',
          media: '/api/v1/zalo/webhook/media/v/{code}.jpg',
        });
      }
    }

    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const secret = env.ZALO_WEBHOOK_SECRET || '';
    if (!secret) {
      return Response.json({ ok: false, error: 'ZALO_WEBHOOK_SECRET not set on Worker' }, { status: 500 });
    }

    const body = await request.text();
    const originUrl = `https://${url.host}/api/v1/zalo/webhook-origin`;

    const originResponse = await fetch(originUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Bot-Api-Secret-Token': request.headers.get('X-Bot-Api-Secret-Token') || secret,
        'X-Zalo-Proxy-Token': secret,
        'User-Agent': 'Cloudflare-Workers-Zalo-Proxy/1.0',
      },
      body,
    });

    const responseBody = await originResponse.text();
    return new Response(responseBody, {
      status: originResponse.status,
      headers: { 'Content-Type': 'application/json' },
    });
  },
};

async function proxyMediaOrigin(request, url, originPath) {
  const originUrl = `https://${url.host}${originPath}${url.search}`;
  const originResponse = await fetch(originUrl, {
    method: request.method,
    headers: {
      Accept: request.headers.get('Accept') || '*/*',
      Range: request.headers.get('Range') || '',
      'User-Agent': 'Cloudflare-Workers-Zalo-Media-Proxy/1.0',
    },
  });
  return new Response(originResponse.body, {
    status: originResponse.status,
    headers: originResponse.headers,
  });
}
