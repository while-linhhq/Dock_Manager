/**
 * @deprecated Use zalo-platform-worker.js (webhook + media proxy).
 * Cloudflare Worker — proxy Zalo webhook past error 1010 (Java User-Agent block).
 *
 * Deploy:
 * 1. Workers & Pages → Create Worker → paste this file
 * 2. Settings → Variables: ZALO_WEBHOOK_SECRET = same as server .env
 * 3. Triggers → Add route: api-basondock.iotforce.io.vn/api/v1/zalo/webhook*
 * 4. Server: ZALO_POLLING_ENABLED=false, restart, POST /api/v1/zalo/webhook/register
 *
 * Flow: Zalo → Worker (/webhook) → origin (/webhook-origin) with clean User-Agent
 */
export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === 'GET') {
      return Response.json({
        ok: true,
        message: 'Zalo webhook via Cloudflare Worker',
        forward: '/api/v1/zalo/webhook-origin',
      });
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
