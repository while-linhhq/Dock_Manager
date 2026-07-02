"""Cap CPU threads for math/CV libs to stop oversubscription.

Problem: torch, paddle, OpenCV, numpy/OpenBLAS each spawn a thread pool sized to
the core count by default. Running them together oversubscribes the CPU (e.g. load
20 on a 16-thread box), so threads fight over cores, context-switch overhead climbs,
and per-frame latency *rises* even though CPU shows near 100%.

Fix: bound each pool so their sum is close to the physical budget.

Two phases:
- ``apply_thread_env_caps()``  — sets env vars (OMP/MKL/OpenBLAS/NUMEXPR). MUST run
  BEFORE numpy/torch/cv2/paddle are first imported (these read the env at import time).
- ``apply_runtime_thread_caps()`` — calls torch.set_num_threads / cv2.setNumThreads.
  Run AFTER those libs are imported (safe to call once the app is up).

Override any value via env: DOCK_OMP_THREADS, DOCK_TORCH_THREADS, DOCK_CV2_THREADS.
If env is absent, values come from port_configs (thread_* keys). Set
DOCK_THREAD_CAPS=0 or port_config thread_caps_enabled=false to disable entirely.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# Defaults tuned for a ~16-thread desktop CPU (e.g. i5-13400F) running
# YOLO+DINOv2 (GPU, CPU pre/post) in the main process and PaddleOCR in a child.
# Keep the sum well under the thread count so the two processes don't collide.
_DEFAULT_OMP_THREADS = 4
_DEFAULT_TORCH_THREADS = 4
_DEFAULT_CV2_THREADS = 2

# Smaller budget for the OCR subprocess (paddle CPU ops + its own opencv).
_DEFAULT_OCR_OMP_THREADS = 3
_DEFAULT_OCR_CV2_THREADS = 2


def _bool_from_raw(raw: str, default: bool) -> bool:
    value = raw.strip().lower()
    if value in ('1', 'true', 'yes', 'on'):
        return True
    if value in ('0', 'false', 'no', 'off'):
        return False
    return default


def _caps_enabled() -> bool:
    env = os.environ.get('DOCK_THREAD_CAPS')
    if env is not None and env.strip():
        return _bool_from_raw(env, True)
    try:
        from app.utils.port_config_runtime import get_port_bool

        return get_port_bool('thread_caps_enabled', True)
    except Exception:
        return True


def _env_int(name: str, default: int, *, port_key: str | None = None) -> int:
    raw = os.environ.get(name, '').strip()
    if not raw and port_key:
        try:
            from app.utils.port_config_runtime import get_port_config

            raw = get_port_config(port_key, '').strip()
        except Exception:
            raw = ''
    if not raw:
        return default
    try:
        value = int(raw)
        return value if value > 0 else default
    except ValueError:
        return default


def apply_thread_env_caps(*, ocr_subprocess: bool = False) -> dict[str, str]:
    """Set OMP/MKL/OpenBLAS/NUMEXPR thread env vars.

    Call at the very top of a process entrypoint, before importing numpy/torch/
    cv2/paddle. Returns the env keys that were set (for logging).
    """
    if not _caps_enabled():
        return {}

    omp_default = _DEFAULT_OCR_OMP_THREADS if ocr_subprocess else _DEFAULT_OMP_THREADS
    omp = _env_int(
        'DOCK_OMP_THREADS',
        omp_default,
        port_key='thread_ocr_omp_threads' if ocr_subprocess else 'thread_omp_threads',
    )

    caps = {
        'OMP_NUM_THREADS': str(omp),
        'OPENBLAS_NUM_THREADS': str(omp),
        'MKL_NUM_THREADS': str(omp),
        'NUMEXPR_NUM_THREADS': str(omp),
        'VECLIB_MAXIMUM_THREADS': str(omp),
    }
    # Only set if not already provided by the operator, so external overrides win.
    applied: dict[str, str] = {}
    for key, value in caps.items():
        if os.environ.get(key, '').strip():
            continue
        os.environ[key] = value
        applied[key] = value
    return applied


def apply_runtime_thread_caps(*, ocr_subprocess: bool = False) -> None:
    """Cap torch + OpenCV thread pools. Call AFTER torch/cv2 are importable."""
    if not _caps_enabled():
        return

    torch_default = _DEFAULT_OCR_OMP_THREADS if ocr_subprocess else _DEFAULT_TORCH_THREADS
    cv2_default = _DEFAULT_OCR_CV2_THREADS if ocr_subprocess else _DEFAULT_CV2_THREADS
    torch_threads = _env_int(
        'DOCK_TORCH_THREADS',
        torch_default,
        port_key='thread_ocr_omp_threads' if ocr_subprocess else 'thread_torch_threads',
    )
    cv2_threads = _env_int(
        'DOCK_CV2_THREADS',
        cv2_default,
        port_key='thread_ocr_cv2_threads' if ocr_subprocess else 'thread_cv2_threads',
    )

    try:
        import torch

        torch.set_num_threads(torch_threads)
        # Inter-op pool is for parallel graph branches; keep small.
        try:
            torch.set_num_interop_threads(max(1, torch_threads // 2))
        except (RuntimeError, AttributeError):
            # set_num_interop_threads raises if called after parallel work started.
            pass
    except Exception as err:  # torch may be absent in some contexts
        logger.debug('thread_limits: torch cap skipped: %s', err)

    try:
        import cv2

        cv2.setNumThreads(cv2_threads)
    except Exception as err:
        logger.debug('thread_limits: cv2 cap skipped: %s', err)

    logger.info(
        'thread_limits: caps applied (ocr_subprocess=%s) torch=%s cv2=%s omp=%s',
        ocr_subprocess,
        torch_threads,
        cv2_threads,
        os.environ.get('OMP_NUM_THREADS', '<unset>'),
    )
