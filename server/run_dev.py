"""
Chạy API trong dev. Ưu tiên dùng thay cho `uvicorn app.main:app` thuần trên Windows
để giảm traceback CancelledError/KeyboardInterrupt khi Ctrl+C.

  cd server
  python run_dev.py

Biến môi trường: HOST, PORT, UVICORN_RELOAD (1/0), GRACEFUL_SHUTDOWN (giây).
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path


def main() -> None:
    server_root = Path(__file__).resolve().parent
    os.chdir(server_root)
    sr = str(server_root)
    if sr not in sys.path:
        sys.path.insert(0, sr)

    if sys.platform == 'win32':
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except (AttributeError, NotImplementedError):
            pass

    import uvicorn

    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', '8000'))
    reload = os.environ.get('UVICORN_RELOAD', '1').lower() not in ('0', 'false', 'no', 'off')
    graceful = int(os.environ.get('GRACEFUL_SHUTDOWN', '5'))

    try:
        uvicorn.run(
            'app.main:app',
            host=host,
            port=port,
            reload=reload,
            timeout_graceful_shutdown=graceful,
        )
    except TypeError:
        # uvicorn < 0.29: không có timeout_graceful_shutdown
        uvicorn.run('app.main:app', host=host, port=port, reload=reload)


if __name__ == '__main__':
    main()
