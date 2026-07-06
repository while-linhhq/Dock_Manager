"""
Chạy API trong dev. Ưu tiên dùng thay cho `uvicorn app.main:app` thuần trên Windows
để giảm traceback CancelledError/KeyboardInterrupt khi Ctrl+C.

  cd server
  python run_dev.py

Biến môi trường: HOST, PORT, UVICORN_RELOAD (1/0), GRACEFUL_SHUTDOWN (giây).
  AUTOSTART_PIPELINE (1/0, default 1)  — tự bắt đầu pipeline sau khi server sẵn sàng.
  AUTOSTART_DELAY_SEC (giây, default 10) — trễ trước khi auto-start.
  AUTOSTART_GROUP_ID (int)             — group cố định; bỏ trống = group active mới nhất.
  AUTOSTART_ENABLE_OCR (1/0, default 1)
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
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


def _env_flag(name: str, default: str = '1') -> bool:
    return os.environ.get(name, default).strip().lower() not in ('0', 'false', 'no', 'off')


def _resolve_autostart_group_id(base_url: str) -> int | None:
    """Thứ tự ưu tiên: env AUTOSTART_GROUP_ID > port_configs.autostart_group_id
    > group active mới nhất (get_all order id desc)."""
    fixed = os.environ.get('AUTOSTART_GROUP_ID', '').strip()
    if fixed:
        try:
            return int(fixed)
        except ValueError:
            logger.warning('AUTOSTART_GROUP_ID=%r không phải số — bỏ qua', fixed)
    try:
        from app.db.session import SessionLocal
        from app.repositories.camera_group_repository import camera_group_repo
        from app.repositories.port_config_repository import port_config_repo

        with SessionLocal() as db:
            # DB-configured default group (đặt qua port_configs, chỉnh được trên UI).
            try:
                cfg_rows = port_config_repo.get_all(db)
                cfg_map = {row.key: row.value for row in cfg_rows}
                raw_default = (cfg_map.get('autostart_group_id', '') or '').strip()
                if raw_default:
                    configured_id = int(raw_default)
                    group = camera_group_repo.get(db, configured_id)
                    if group is not None and bool(group.is_active):
                        enabled = [
                            m for m in group.members
                            if bool(m.enabled) and getattr(m, 'camera', None) is not None
                        ]
                        if enabled:
                            logger.info(
                                'autostart: dùng group mặc định từ port_configs=%s (%s)',
                                configured_id, group.name,
                            )
                            return int(group.id)
                        logger.warning(
                            'autostart: group mặc định %s không có camera enabled — fallback',
                            configured_id,
                        )
                    else:
                        logger.warning(
                            'autostart: group mặc định %s không tồn tại/không active — fallback',
                            raw_default,
                        )
            except Exception as cfg_err:
                logger.warning('autostart: đọc autostart_group_id lỗi (%s) — fallback', cfg_err)

            groups = camera_group_repo.get_all(db, active_only=True)
        for group in groups:
            enabled = [
                m for m in group.members
                if bool(m.enabled) and getattr(m, 'camera', None) is not None
            ]
            if enabled:
                return int(group.id)
        logger.warning('autostart: không có camera group active nào có camera enabled')
    except Exception as err:
        logger.warning('autostart: không lấy được camera group (%s)', err)
    return None


def _wait_server_ready(base_url: str, *, timeout_sec: float) -> bool:
    """Poll /health tới khi API trả 200 (app đã lên) hoặc hết giờ.

    Dùng /health (trả tĩnh {'status':'healthy'}) thay vì /pipeline/status:
    khi pipeline chưa chạy, /pipeline/status chạy full GPU probe (~9s/lần),
    làm readiness poll (timeout ngắn) luôn timeout → auto-start bị bỏ nhầm.
    """
    deadline = time.monotonic() + timeout_sec
    url = f'{base_url}/health'
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(1.0)
    return False


def _autostart_pipeline(host: str, port: int) -> None:
    delay = float(os.environ.get('AUTOSTART_DELAY_SEC', '10'))
    enable_ocr = _env_flag('AUTOSTART_ENABLE_OCR', '1')
    connect_host = '127.0.0.1' if host in ('0.0.0.0', '::', '') else host
    base_url = f'http://{connect_host}:{port}'

    # Chờ đủ delay VÀ tới khi API sẵn sàng (app lifespan xong) trước khi gọi.
    time.sleep(delay)
    if not _wait_server_ready(base_url, timeout_sec=60):
        logger.warning('autostart: server chưa sẵn sàng sau khi chờ — bỏ auto-start')
        return

    # Nếu đã chạy (vd. UI bấm Start trước) thì không đụng vào.
    try:
        import json

        with urllib.request.urlopen(f'{base_url}/api/v1/pipeline/status', timeout=15) as resp:
            status = json.loads(resp.read().decode('utf-8'))
        if status.get('is_running'):
            logger.info('autostart: pipeline đã chạy — bỏ qua')
            return
    except Exception:
        pass

    group_id = _resolve_autostart_group_id(base_url)
    if group_id is None:
        return

    import json

    payload = json.dumps({'camera_group_id': group_id, 'enable_ocr': enable_ocr}).encode('utf-8')
    req = urllib.request.Request(
        f'{base_url}/api/v1/pipeline/start',
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode('utf-8')
        logger.info('autostart: pipeline start group=%s -> %s', group_id, body)
    except urllib.error.HTTPError as err:
        logger.warning(
            'autostart: start thất bại group=%s (%s): %s',
            group_id, err.code, err.read().decode('utf-8', 'replace'),
        )
    except Exception as err:
        logger.warning('autostart: start lỗi group=%s (%s)', group_id, err)


def _maybe_start_autostart_thread(host: str, port: int, *, reload: bool) -> None:
    if not _env_flag('AUTOSTART_PIPELINE', '1'):
        return
    # Với reload=1 uvicorn fork reloader + worker; chỉ chạy trong tiến trình worker
    # (RUN_MAIN) để tránh gọi start 2 lần.
    if reload and os.environ.get('RUN_MAIN') != 'true':
        return
    thread = threading.Thread(
        target=_autostart_pipeline,
        args=(host, port),
        name='pipeline-autostart',
        daemon=True,
    )
    thread.start()
    logger.info('autostart: đã lên lịch bắt đầu pipeline sau %ss', os.environ.get('AUTOSTART_DELAY_SEC', '10'))


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

    _maybe_start_autostart_thread(host, port, reload=reload)

    _run_uvicorn(host, port, reload=reload, graceful=graceful)


if __name__ == '__main__':
    main()
