"""Runtime GPU diagnostics for pipeline startup and /pipeline/status."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal

from app.core.config import settings
from app.utils.port_config_runtime import effective_device, effective_model_path

logger = logging.getLogger(__name__)

DeviceKind = Literal['gpu', 'cpu', 'off', 'n/a']


def _torch_uses_cuda(device: str | None = None) -> bool:
    raw = str(device if device is not None else settings.DEVICE or '0').strip().lower()
    if raw in {'cpu', '-1', 'none'}:
        return False
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _torch_device_label() -> str | None:
    try:
        import torch

        if torch.cuda.is_available():
            return str(torch.cuda.get_device_name(0))
    except Exception:
        return None
    return None


def collect_ai_component_matrix() -> list[dict[str, Any]]:
    """
    Per-component GPU/CPU status for startup banner and diagnostics.
    Does not load heavy models (YOLO/Visual/OCR runtime).
    """
    rows: list[dict[str, Any]] = []

    yolo_device: DeviceKind = 'gpu' if _torch_uses_cuda(effective_device()) else 'cpu'
    # Hiển thị đúng file đang chạy: engine TensorRT nếu có và dùng được, không phải .pt trong cấu hình.
    try:
        from app.utils.ai.yolo_detector import resolve_yolo_weights

        runtime_model, runtime_kind = resolve_yolo_weights(effective_model_path())
        yolo_detail = f'model={runtime_model}' + (' (TensorRT engine)' if runtime_kind == 'engine' else '')
    except Exception:
        yolo_detail = f'model={effective_model_path()}'
    try:
        import torch

        yolo_detail += f' · torch {torch.__version__}'
        if yolo_device == 'gpu':
            label = _torch_device_label()
            if label:
                yolo_detail += f' · {label}'
    except Exception:
        pass
    rows.append(
        {
            'key': 'yolo',
            'name': 'YOLO detection',
            'device': yolo_device,
            'detail': yolo_detail,
        }
    )

    visual_cfg = str(settings.VISUAL_DEVICE or settings.DEVICE or '0').strip()
    visual_device: DeviceKind = 'gpu' if _torch_uses_cuda(visual_cfg) else 'cpu'
    if not settings.ENABLE_VISUAL_ID:
        visual_device = 'off'
    visual_runtime = ''
    if visual_device == 'gpu':
        try:
            from app.services.ai.visual_embedding_extractor import _resolve_engine_path

            engine = _resolve_engine_path(None, str(settings.VISUAL_BACKBONE))
            if engine:
                visual_runtime = f' · engine={Path(engine).name}'
        except Exception:
            visual_runtime = ''
    rows.append(
        {
            'key': 'visual_id',
            'name': 'Visual ID (DINOv2)',
            'device': visual_device,
            'detail': (
                f'backbone={settings.VISUAL_BACKBONE}'
                f' · device_cfg={visual_cfg}'
                f'{visual_runtime}'
            ),
        }
    )

    ocr_device: DeviceKind = 'cpu'
    ocr_detail = 'PaddleOCR · in-process CPU fallback'
    if settings.ENABLE_OCR:
        try:
            from app.utils.ai.ship_id_recognizer import _paddle_gpu_probe_subprocess

            if _paddle_gpu_probe_subprocess():
                ocr_device = 'gpu'
                ocr_detail = 'PaddleOCR · isolated GPU subprocess (torch-safe)'
            else:
                ocr_detail = 'PaddleOCR · CPU (GPU subprocess probe failed)'
        except Exception as exc:
            ocr_detail = f'PaddleOCR · CPU (probe error: {exc})'
    else:
        ocr_device = 'off'
        ocr_detail = 'disabled (ENABLE_OCR=false)'
    rows.append(
        {
            'key': 'ocr',
            'name': 'OCR (ship ID)',
            'device': ocr_device,
            'detail': ocr_detail,
        }
    )

    nvdec_device: DeviceKind = 'off'
    nvdec_detail = 'disabled'
    try:
        from app.utils.ai.rtsp_capture import nvdec_status

        status_text = nvdec_status()
        nvdec_detail = status_text
        if 'enabled' in status_text and 'hwaccel=' in status_text:
            nvdec_device = 'gpu'
        elif 'disabled' in status_text:
            nvdec_device = 'off'
        else:
            nvdec_device = 'cpu'
    except Exception as exc:
        nvdec_detail = f'unavailable ({exc})'
    rows.append(
        {
            'key': 'nvdec',
            'name': 'RTSP decode (NVDEC)',
            'device': nvdec_device,
            'detail': nvdec_detail,
        }
    )

    rows.append(
        {
            'key': 'qdrant',
            'name': 'Qdrant vector search',
            'device': 'cpu',
            'detail': f'{settings.QDRANT_HOST}:{settings.QDRANT_PORT}',
        }
    )

    return rows


def log_ai_component_matrix() -> list[dict[str, Any]]:
    rows = collect_ai_component_matrix()
    log = logging.getLogger('app.startup')
    log.info('  AI stack — GPU / CPU allocation')
    for row in rows:
        device = str(row.get('device') or 'n/a')
        if device == 'gpu':
            badge = 'GPU'
        elif device == 'cpu':
            badge = 'CPU'
        elif device == 'off':
            badge = 'OFF'
        else:
            badge = device.upper()
        log.info(
            '    %-22s [%4s]  %s',
            row.get('name'),
            badge,
            row.get('detail'),
        )
    return rows


def collect_gpu_runtime_status() -> dict[str, Any]:
    status: dict[str, Any] = {
        'nvidia_smi': False,
        'torch_cuda_available': False,
        'paddle_cuda_count': 0,
        'paddle_gpu_ok': False,
        'recommended_ocr_device': 'cpu',
        'device_label': None,
        'errors': [],
        'components': collect_ai_component_matrix(),
    }

    try:
        import subprocess

        proc = subprocess.run(
            ['nvidia-smi', '--query-gpu=name,memory.used,memory.total', '--format=csv,noheader'],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            status['nvidia_smi'] = True
            parts = proc.stdout.strip().split(',')
            if len(parts) >= 3:
                status['device_label'] = parts[0].strip()
                status['vram_used_mib'] = parts[1].strip()
                status['vram_total_mib'] = parts[2].strip()
    except Exception as exc:
        status['errors'].append(f'nvidia-smi: {exc}')

    try:
        import torch

        status['torch_version'] = torch.__version__
        status['torch_cuda_available'] = bool(torch.cuda.is_available())
        if torch.cuda.is_available():
            status['torch_device'] = torch.cuda.get_device_name(0)
    except Exception as exc:
        status['errors'].append(f'torch: {exc}')

    try:
        import paddle

        status['paddle_version'] = paddle.__version__
        status['paddle_cuda_count'] = int(paddle.device.cuda.device_count())
    except Exception as exc:
        status['errors'].append(f'paddle: {exc}')

    try:
        from app.utils.ai.ship_id_recognizer import _paddle_gpu_probe_subprocess

        status['paddle_gpu_ok'] = bool(_paddle_gpu_probe_subprocess())
    except Exception as exc:
        status['errors'].append(f'paddle_probe: {exc}')

    status['recommended_ocr_device'] = 'gpu' if status['paddle_gpu_ok'] else 'cpu'
    return status


def log_gpu_runtime_status(prefix: str = 'pipeline') -> dict[str, Any]:
    status = collect_gpu_runtime_status()
    logger.info(
        '%s GPU: nvidia=%s torch_cuda=%s paddle_cuda=%s paddle_ok=%s device=%s',
        prefix,
        status.get('nvidia_smi'),
        status.get('torch_cuda_available'),
        status.get('paddle_cuda_count'),
        status.get('paddle_gpu_ok'),
        status.get('device_label') or status.get('torch_device'),
    )
    for err in status.get('errors') or []:
        logger.warning('%s GPU probe: %s', prefix, err)
    return status
