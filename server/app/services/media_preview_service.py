from __future__ import annotations

import re

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.services.storage.minio_service import (
    get_object_size,
    guess_content_type,
    open_object_stream,
    open_object_stream_range,
    parse_minio_uri,
)
from app.utils.media_short_link import normalize_short_link_code, resolve_short_media_path
from app.utils.media_token import decode_media_preview_token

_RANGE_RE = re.compile(r'^bytes=(\d*)-(\d*)$')


def _parse_range_header(range_header: str, total_size: int) -> tuple[int, int] | None:
    match = _RANGE_RE.match(str(range_header or '').strip())
    if not match or total_size <= 0:
        return None
    start_raw, end_raw = match.groups()
    start = int(start_raw) if start_raw else 0
    end = int(end_raw) if end_raw else total_size - 1
    if start < 0 or start >= total_size:
        return None
    end = min(end, total_size - 1)
    if end < start:
        return None
    return start, end


def _preview_headers(
    *,
    content_type: str | None,
    minio_path: str,
    total_size: int | None = None,
    start: int | None = None,
    end: int | None = None,
) -> dict[str, str]:
    headers: dict[str, str] = {}
    ctype = str(content_type or '').lower()
    path_lower = str(minio_path or '').lower()
    is_video = ctype.startswith('video/') or path_lower.endswith('.mp4')
    if is_video:
        headers['Content-Type'] = 'video/mp4' if path_lower.endswith('.mp4') else (content_type or 'video/mp4')
        headers['Accept-Ranges'] = 'bytes'
        headers['Content-Disposition'] = 'inline; filename="detection.mp4"'
        if start is not None and end is not None and total_size is not None:
            headers['Content-Range'] = f'bytes {start}-{end}/{total_size}'
            headers['Content-Length'] = str(end - start + 1)
        elif total_size is not None:
            headers['Content-Length'] = str(total_size)
    elif ctype.startswith('image/'):
        headers['Content-Type'] = content_type or 'image/jpeg'
        headers['Content-Disposition'] = 'inline'
        if total_size is not None:
            headers['Content-Length'] = str(total_size)
    # Avoid Cloudflare caching 404/200 for hours (stale "Not Found" in Zalo browser).
    headers['Cache-Control'] = 'private, no-store, must-revalidate'
    return headers


def stream_minio_media(
    minio_path: str,
    *,
    request: Request | None = None,
    head_only: bool = False,
) -> Response:
    if parse_minio_uri(minio_path) is None:
        raise HTTPException(status_code=404, detail='Invalid media path')

    total_size = get_object_size(minio_path)
    if total_size is None:
        raise HTTPException(status_code=404, detail='Media not found')

    range_header = request.headers.get('range') if request else None
    parsed_range = _parse_range_header(range_header, total_size) if range_header else None

    if parsed_range:
        start, end = parsed_range
        length = end - start + 1
        ref = parse_minio_uri(minio_path)
        content_type = guess_content_type(ref.object_key) if ref else None
        headers = _preview_headers(
            content_type=content_type,
            minio_path=minio_path,
            total_size=total_size,
            start=start,
            end=end,
        )
        if head_only:
            return Response(status_code=206, headers=headers, media_type=headers.get('Content-Type'))

        response, content_type = open_object_stream_range(minio_path, offset=start, length=length)
        if response is None:
            raise HTTPException(status_code=404, detail='Media not found')

        def iter_chunks(chunk_size: int = 64 * 1024):
            try:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
            finally:
                response.close()
                response.release_conn()

        return StreamingResponse(
            iter_chunks(),
            status_code=206,
            media_type=headers.get('Content-Type', content_type or 'application/octet-stream'),
            headers=headers,
        )

    ref = parse_minio_uri(minio_path)
    content_type = guess_content_type(ref.object_key) if ref else None
    headers = _preview_headers(
        content_type=content_type,
        minio_path=minio_path,
        total_size=total_size,
    )
    if head_only:
        return Response(status_code=200, headers=headers, media_type=headers.get('Content-Type'))

    response, content_type = open_object_stream(minio_path)
    if response is None:
        raise HTTPException(status_code=404, detail='Media not found')

    def iter_chunks(chunk_size: int = 64 * 1024):
        try:
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                yield chunk
        finally:
            response.close()
            response.release_conn()

    headers = _preview_headers(
        content_type=content_type,
        minio_path=minio_path,
        total_size=total_size,
    )
    return StreamingResponse(
        iter_chunks(),
        media_type=headers.get('Content-Type', content_type or 'application/octet-stream'),
        headers=headers,
    )


_NO_STORE_HEADERS = {'Cache-Control': 'private, no-store, must-revalidate'}


def serve_short_media(code: str, request: Request) -> Response:
    normalized = normalize_short_link_code(code)
    minio_path = resolve_short_media_path(normalized)
    if not minio_path:
        return JSONResponse(
            status_code=404,
            content={'detail': 'Short link not found or expired'},
            headers=_NO_STORE_HEADERS,
        )
    return stream_minio_media(
        minio_path,
        request=request,
        head_only=request.method == 'HEAD',
    )


def serve_preview_media(token: str, request: Request) -> Response:
    minio_path = decode_media_preview_token(token)
    if not minio_path:
        return JSONResponse(
            status_code=403,
            content={'detail': 'Invalid or expired token'},
            headers=_NO_STORE_HEADERS,
        )
    return stream_minio_media(
        minio_path,
        request=request,
        head_only=request.method == 'HEAD',
    )
