from __future__ import annotations

from fastapi import APIRouter, Request

from app.services.media_preview_service import serve_preview_media, serve_short_media

router = APIRouter()


@router.api_route('/v/{code}', methods=['GET', 'HEAD'])
@router.api_route('/v/{code}.{ext}', methods=['GET', 'HEAD'])
def short_media(code: str, request: Request, ext: str = ''):
    return serve_short_media(code, request)


@router.api_route('/origin/v/{code}', methods=['GET', 'HEAD'])
@router.api_route('/origin/v/{code}.{ext}', methods=['GET', 'HEAD'])
def short_media_origin(code: str, request: Request, ext: str = ''):
    """Origin-only path for Cloudflare Worker media proxy (Java UA bypass)."""
    return serve_short_media(code, request)


@router.api_route('/preview/{token:path}', methods=['GET', 'HEAD'])
def preview_media(token: str, request: Request):
    return serve_preview_media(token, request)


@router.api_route('/origin/preview/{token:path}', methods=['GET', 'HEAD'])
def preview_media_origin(token: str, request: Request):
    """Origin-only path for Cloudflare Worker media proxy (Java UA bypass)."""
    return serve_preview_media(token, request)
