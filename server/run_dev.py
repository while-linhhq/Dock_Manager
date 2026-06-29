"""
Chạy API trong dev. Ưu tiên dùng thay cho `uvicorn app.main:app` thuần trên Windows
để giảm traceback CancelledError/KeyboardInterrupt khi Ctrl+C.

  cd server
  python run_dev.py

Biến môi trường: HOST, PORT, UVICORN_RELOAD (1/0), GRACEFUL_SHUTDOWN (giây).
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _resolve_bind_host(raw: str) -> str:
    host = (raw or '127.0.0.1').strip() or '127.0.0.1'
    if host in {'127.0.0.1', '0.0.0.0', '::', '::1'}:
        return host
    try:
        socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError as err:
        logger.warning('HOST=%r not resolvable (%s) — using 127.0.0.1', host, err)
        return '127.0.0.1'
    return host


def _run_uvicorn(host: str, port: int, *, reload: bool, graceful: int) -> None:
    import uvicorn

    kwargs = {
        'host': host,
        'port': port,
        'reload': reload,
        # wsproto avoids websockets legacy drain AssertionError on abrupt client close.
        'ws': 'wsproto',
        # App-level 'ka' keepalive; disable uvicorn ping to avoid concurrent drain races.
        'ws_ping_interval': None,
        'ws_ping_timeout': None,
    }
    try:
        uvicorn.run(
            'app.main:app',
            timeout_graceful_shutdown=graceful,
            **kwargs,
        )
    except TypeError:
        # uvicorn < 0.29: no timeout_graceful_shutdown / ws_ping / ws kwargs
        kwargs.pop('ws_ping_interval', None)
        kwargs.pop('ws_ping_timeout', None)
        kwargs.pop('ws', None)
        try:
            uvicorn.run('app.main:app', timeout_graceful_shutdown=graceful, **kwargs)
        except TypeError:
            uvicorn.run('app.main:app', host=host, port=port, reload=reload)


def main() -> None:
    server_root = Path(__file__).resolve().parent
    os.chdir(server_root)
    sr = str(server_root)
    if sr not in sys.path:
        sys.path.insert(0, sr)

    # In-process CUDA path setup (no os.execve). reexec broke DNS/getaddrinfo on some hosts.
    from app.utils.ai.gpu_bootstrap import init_cuda_library_path

    init_cuda_library_path('pre')

    if sys.platform == 'win32':
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except (AttributeError, NotImplementedError):
            pass

    host = _resolve_bind_host(os.environ.get('HOST', '127.0.0.1'))
    port = int(os.environ.get('PORT', '8000'))
    # Hot-reload + GPU pipeline (YOLO/Paddle) often freezes the machine; use UVICORN_RELOAD=0 while testing AI.
    reload = os.environ.get('UVICORN_RELOAD', '0').lower() not in ('0', 'false', 'no', 'off')
    graceful = int(os.environ.get('GRACEFUL_SHUTDOWN', '15'))

    _run_uvicorn(host, port, reload=reload, graceful=graceful)


if __name__ == '__main__':
    main()
