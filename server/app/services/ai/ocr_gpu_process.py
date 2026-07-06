"""PaddleOCR in an isolated subprocess so GPU works alongside torch (YOLO/DINOv2)."""

from __future__ import annotations

import logging
import multiprocessing as mp
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_SERVER_ROOT = Path(__file__).resolve().parents[3]
_STARTUP_TIMEOUT_SEC = 180.0
_RECOGNIZE_TIMEOUT_SEC = 45.0
_PROBE_SHAPE = (64, 128, 3)


def _probe_recognizer(recognizer, probe: np.ndarray) -> None:
    from app.utils.ai.paddle_ocr_adapter import run_ocr_lines

    run_ocr_lines(recognizer.ocr, recognizer._ensure_min_side_bgr(probe))
    recognizer.recognize_bgr(probe)


def _load_rule_engine():
    from app.db.session import SessionLocal
    from app.services.ai.ship_id_rule_engine import get_rule_engine

    engine = get_rule_engine()
    try:
        with SessionLocal() as db:
            engine.reload(db)
    except Exception as exc:
        logger.warning('OCR subprocess: rule engine load failed: %s', exc)
    return engine


def _init_recognizer():
    from app.utils.ai.gpu_bootstrap import init_cuda_library_path
    from app.utils.ai.ship_id_recognizer import ShipIdRecognizer

    init_cuda_library_path('pre')
    rule_engine = _load_rule_engine()
    probe = np.zeros(_PROBE_SHAPE, dtype=np.uint8)

    for use_gpu in (True, False):
        try:
            recognizer = ShipIdRecognizer(
                rule_engine=rule_engine,
                use_gpu=use_gpu,
                assume_gpu_available=use_gpu,
            )
            _probe_recognizer(recognizer, probe)
            device = 'gpu' if use_gpu else 'cpu'
            return recognizer, device
        except Exception as exc:
            if not use_gpu:
                raise
            logger.warning('OCR GPU probe failed in subprocess, retrying CPU: %s', exc)

    raise RuntimeError('OCR subprocess init failed')


def _ocr_subprocess_main(
    request_q: mp.Queue,
    response_q: mp.Queue,
    startup_q: mp.Queue,
) -> None:
    os.chdir(_SERVER_ROOT)
    if str(_SERVER_ROOT) not in sys.path:
        sys.path.insert(0, str(_SERVER_ROOT))

    # Cap thread pools in the child too (spawn re-imports torch+paddle+cv2).
    # Smaller budget than the main process so the two don't oversubscribe together.
    from app.utils.ai.thread_limits import (
        apply_runtime_thread_caps,
        apply_thread_env_caps,
    )

    apply_thread_env_caps(ocr_subprocess=True, force=True)

    recognizer = None
    device = 'cpu'
    try:
        recognizer, device = _init_recognizer()
        apply_runtime_thread_caps(ocr_subprocess=True)
        startup_q.put({'ok': True, 'device': device})
    except Exception as exc:
        logger.exception('OCR GPU subprocess init failed')
        startup_q.put({'ok': False, 'error': str(exc)})
        return

    from app.services.ai.ship_id_rule_engine import get_rule_engine
    from app.utils.ai.ship_id_recognizer import ShipIdRecognizer

    rule_engine = get_rule_engine()
    last_rule_reload = time.monotonic()
    rule_reload_interval = 30.0

    def _recognize_with_fallback(crop: np.ndarray) -> tuple[list[dict[str, Any]], str]:
        nonlocal recognizer, device
        try:
            return list(recognizer.recognize_bgr(crop) or []), device
        except Exception as gpu_exc:
            if device != 'gpu':
                raise
            logger.warning(
                'OCR GPU inference failed in subprocess, switching to CPU: %s',
                gpu_exc,
            )
            recognizer = ShipIdRecognizer(rule_engine=rule_engine, use_gpu=False)
            device = 'cpu'
            return list(recognizer.recognize_bgr(crop) or []), device

    while True:
        try:
            msg = request_q.get()
        except (EOFError, KeyboardInterrupt):
            break
        if not isinstance(msg, dict):
            continue
        cmd = str(msg.get('cmd') or '').strip().lower()
        if cmd in ('shutdown', 'stop'):
            break
        if cmd != 'recognize':
            continue

        now_mono = time.monotonic()
        if now_mono - last_rule_reload >= rule_reload_interval:
            try:
                from app.db.session import SessionLocal

                with SessionLocal() as db:
                    rule_engine.reload(db)
            except Exception as exc:
                logger.warning('OCR subprocess: rule engine reload failed: %s', exc)
            last_rule_reload = now_mono

        req_id = str(msg.get('req_id') or '')
        try:
            shape = tuple(int(v) for v in msg.get('shape') or ())
            raw = msg.get('data')
            if not shape or not isinstance(raw, (bytes, bytearray)):
                raise ValueError('invalid crop payload')
            crop = np.frombuffer(raw, dtype=np.uint8).reshape(shape)
            result, active_device = _recognize_with_fallback(crop)
            response_q.put(
                {
                    'req_id': req_id,
                    'ok': True,
                    'result': result,
                    'device': active_device,
                }
            )
        except Exception as exc:
            logger.exception('OCR subprocess recognize failed req_id=%s', req_id)
            response_q.put(
                {'req_id': req_id, 'ok': False, 'error': str(exc), 'result': []}
            )


class OcrGpuProcessClient:
    """Drop-in for ShipIdRecognizer — runs PaddleOCR in a child process."""

    def __init__(self) -> None:
        self._ctx = mp.get_context('spawn')
        self._request_q: mp.Queue = self._ctx.Queue(maxsize=32)
        self._response_q: mp.Queue = self._ctx.Queue(maxsize=32)
        self._startup_q: mp.Queue = self._ctx.Queue(maxsize=1)
        self._proc: mp.Process | None = None
        self._device = 'cpu'
        self._started = False
        self._cpu_fallback: Any | None = None

    @property
    def device(self) -> str:
        if self._cpu_fallback is not None:
            return 'cpu'
        return self._device

    @property
    def started(self) -> bool:
        return self._started or self._cpu_fallback is not None

    def start(self, *, timeout_sec: float = _STARTUP_TIMEOUT_SEC) -> bool:
        if self._started:
            return True

        from app.utils.ai.gpu_bootstrap import apply_env_patch, prepare_paddle_subprocess_env, restore_env_patch

        env_patch = prepare_paddle_subprocess_env()
        saved_env = apply_env_patch(env_patch)
        try:
            self._proc = self._ctx.Process(
                target=_ocr_subprocess_main,
                args=(self._request_q, self._response_q, self._startup_q),
                daemon=True,
                name='ocr-gpu-worker',
            )
            self._proc.start()
        finally:
            restore_env_patch(saved_env)

        try:
            startup = self._startup_q.get(timeout=max(5.0, float(timeout_sec)))
        except Exception as exc:
            logger.warning('OCR GPU subprocess startup timed out: %s', exc)
            self.close()
            return False

        if not startup.get('ok'):
            logger.warning(
                'OCR GPU subprocess startup failed: %s',
                startup.get('error') or 'unknown',
            )
            self.close()
            return False

        self._device = str(startup.get('device') or 'cpu')
        self._started = True
        logger.info(
            'OCR GPU subprocess ready pid=%s device=%s',
            getattr(self._proc, 'pid', None),
            self._device,
        )
        return True

    def _activate_inprocess_cpu_fallback(self) -> None:
        from app.services.ai.ship_id_rule_engine import get_rule_engine
        from app.utils.ai.ship_id_recognizer import ShipIdRecognizer

        if self._cpu_fallback is None:
            logger.warning('OCR falling back to in-process CPU (legacy path)')
            self._cpu_fallback = ShipIdRecognizer(
                rule_engine=get_rule_engine(),
                use_gpu=False,
            )
        self.close()

    def recognize_bgr(self, img_bgr: np.ndarray) -> list[dict[str, Any]]:
        if self._cpu_fallback is not None:
            return list(self._cpu_fallback.recognize_bgr(img_bgr) or [])

        if not self._started or self._proc is None or not self._proc.is_alive():
            self._activate_inprocess_cpu_fallback()
            return list(self._cpu_fallback.recognize_bgr(img_bgr) or [])

        req_id = uuid.uuid4().hex
        payload = {
            'cmd': 'recognize',
            'req_id': req_id,
            'shape': tuple(int(v) for v in img_bgr.shape),
            'data': img_bgr.tobytes(),
        }
        self._request_q.put(payload)

        deadline = time.monotonic() + _RECOGNIZE_TIMEOUT_SEC
        while time.monotonic() < deadline:
            remaining = max(0.05, deadline - time.monotonic())
            try:
                resp = self._response_q.get(timeout=remaining)
            except Exception as exc:
                logger.warning('OCR subprocess timeout, using in-process CPU: %s', exc)
                self._activate_inprocess_cpu_fallback()
                return list(self._cpu_fallback.recognize_bgr(img_bgr) or [])

            if str(resp.get('req_id') or '') != req_id:
                logger.warning(
                    'OCR GPU subprocess stray response req_id=%s', resp.get('req_id')
                )
                continue
            if not resp.get('ok'):
                logger.warning(
                    'OCR subprocess recognize error req_id=%s: %s — in-process CPU',
                    req_id,
                    resp.get('error'),
                )
                self._activate_inprocess_cpu_fallback()
                return list(self._cpu_fallback.recognize_bgr(img_bgr) or [])

            active_device = str(resp.get('device') or self._device)
            if active_device != self._device:
                self._device = active_device
                logger.info('OCR subprocess switched device=%s', self._device)

            result = resp.get('result')
            return list(result) if isinstance(result, list) else []

        logger.warning('OCR subprocess deadline exceeded — in-process CPU')
        self._activate_inprocess_cpu_fallback()
        return list(self._cpu_fallback.recognize_bgr(img_bgr) or [])

    def close(self) -> None:
        if self._proc is not None and self._proc.is_alive():
            try:
                self._request_q.put({'cmd': 'shutdown'})
            except Exception:
                pass
            self._proc.join(timeout=3.0)
            if self._proc.is_alive():
                self._proc.terminate()
                self._proc.join(timeout=2.0)
        self._proc = None
        self._started = False
        if self._cpu_fallback is not None:
            try:
                self._cpu_fallback.close()
            except Exception:
                pass
            self._cpu_fallback = None
