from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, Request

from app.core.config import settings
from app.services import zalo_service
from app.services.media_preview_service import serve_preview_media, serve_short_media

_log = logging.getLogger('app.api.zalo')

router = APIRouter()


def _validate_webhook_secret(secret_token: str | None) -> None:
    expected = str(settings.ZALO_WEBHOOK_SECRET or '').strip()
    if not expected:
        raise HTTPException(status_code=503, detail='Zalo webhook secret is not configured')
    if str(secret_token or '').strip() != expected:
        raise HTTPException(status_code=403, detail='Unauthorized')


@router.get('/webhook')
def zalo_webhook_get():
    """Webhook chi nhan POST tu Zalo — mo bang browser (GET) se thay thong bao nay."""
    return {
        'ok': True,
        'message': 'Zalo webhook endpoint. Chi nhan POST tu Zalo Bot Platform.',
        'register': 'POST /api/v1/zalo/webhook/register',
        'setup': 'GET /api/v1/zalo/setup',
    }


@router.post('/webhook')
async def zalo_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_bot_api_secret_token: str | None = Header(default=None, alias='X-Bot-Api-Secret-Token'),
):
    """
    Zalo Bot webhook — nhận tin nhắn từ quản lý.
    Doc: https://bot.zaloplatforms.com/docs/webhook
    """
    _validate_webhook_secret(x_bot_api_secret_token)

    try:
        body = await request.json()
    except Exception:
        return {'ok': True, 'result': {'ignored': True}}

    if isinstance(body, dict):
        background_tasks.add_task(zalo_service.process_incoming_payload, body)

    return {'ok': True}


@router.post('/webhook-origin')
async def zalo_webhook_origin(
    request: Request,
    background_tasks: BackgroundTasks,
    x_bot_api_secret_token: str | None = Header(default=None, alias='X-Bot-Api-Secret-Token'),
    x_zalo_proxy_token: str | None = Header(default=None, alias='X-Zalo-Proxy-Token'),
):
    """
    Internal origin target for Cloudflare Worker proxy.
    Worker forwards Zalo payload here with a clean User-Agent (bypasses CF error 1010).
    """
    proxy_secret = str(settings.ZALO_WEBHOOK_SECRET or '').strip()
    if not proxy_secret or str(x_zalo_proxy_token or '').strip() != proxy_secret:
        raise HTTPException(status_code=403, detail='Unauthorized')

    _validate_webhook_secret(x_bot_api_secret_token)

    try:
        body = await request.json()
    except Exception:
        return {'ok': True, 'result': {'ignored': True}}

    if isinstance(body, dict):
        background_tasks.add_task(zalo_service.process_incoming_payload, body)

    return {'ok': True}


@router.api_route('/webhook/media/v/{code}', methods=['GET', 'HEAD'])
@router.api_route('/webhook/media/v/{code}.{ext}', methods=['GET', 'HEAD'])
def zalo_webhook_short_media(code: str, request: Request, ext: str = ''):
    """
    Public media URL for Zalo sendPhoto (proxied by Cloudflare Worker on webhook* route).
    """
    return serve_short_media(code, request)


@router.api_route('/webhook/media/preview/{token:path}', methods=['GET', 'HEAD'])
def zalo_webhook_preview_media(token: str, request: Request):
    return serve_preview_media(token, request)


@router.api_route('/media/origin/v/{code}', methods=['GET', 'HEAD'])
@router.api_route('/media/origin/v/{code}.{ext}', methods=['GET', 'HEAD'])
def zalo_media_origin_short(code: str, request: Request, ext: str = ''):
    """Worker origin fetch target — not for direct Zalo access."""
    return serve_short_media(code, request)


@router.api_route('/media/origin/preview/{token:path}', methods=['GET', 'HEAD'])
def zalo_media_origin_preview(token: str, request: Request):
    return serve_preview_media(token, request)


@router.get('/setup')
def zalo_setup():
    """Trả về webhook URL, bot_id và trạng thái cấu hình Zalo."""
    return zalo_service.get_setup_info()


@router.post('/webhook/register')
def zalo_register_webhook():
    """Đăng ký webhook với Zalo (tat ZALO_POLLING_ENABLED truoc khi dung)."""
    if settings.ZALO_POLLING_ENABLED:
        raise HTTPException(
            status_code=400,
            detail='ZALO_POLLING_ENABLED=true — tat polling truoc khi dang ky webhook',
        )
    try:
        return zalo_service.register_webhook()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        _log.exception('Zalo setWebhook failed')
        raise HTTPException(status_code=502, detail='Failed to register Zalo webhook') from exc


@router.get('/webhook/info')
def zalo_webhook_info():
    try:
        return zalo_service.get_webhook_info()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        _log.exception('Zalo getWebhookInfo failed')
        raise HTTPException(status_code=502, detail='Failed to fetch Zalo webhook info') from exc


@router.post('/test-message')
def zalo_test_message(
    chat_id: str | None = Query(default=None, description='Zalo chat ID (optional)'),
    text: str | None = Query(default=None, description='Noi dung tin nhan test'),
):
    try:
        return zalo_service.send_test_message(chat_id=chat_id, text=text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        _log.exception('Zalo test message failed')
        raise HTTPException(status_code=502, detail='Failed to send Zalo test message') from exc


@router.post('/test-unknown-notification')
def zalo_test_unknown_notification(
    detection_id: int = Query(..., description='Detection ID to simulate'),
    force: bool = Query(default=True, description='Resend even if already notified'),
):
    """Gui goi tin xac nhan UNKNOWN (anh camera don + video + menu)."""
    try:
        return zalo_service.send_test_unknown_notification(detection_id, force=force)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        _log.exception('Zalo test unknown notification failed')
        raise HTTPException(status_code=502, detail='Failed to send Zalo notification') from exc
