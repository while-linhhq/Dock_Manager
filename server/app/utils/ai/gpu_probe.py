"""Runtime GPU diagnostics for pipeline startup and /pipeline/status."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def collect_gpu_runtime_status() -> dict[str, Any]:
    status: dict[str, Any] = {
        'nvidia_smi': False,
        'torch_cuda_available': False,
        'paddle_cuda_count': 0,
        'paddle_gpu_ok': False,
        'recommended_ocr_device': 'cpu',
        'device_label': None,
        'errors': [],
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
        from app.utils.ai.ship_id_recognizer import _gpu_actually_works

        status['paddle_gpu_ok'] = bool(_gpu_actually_works())
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
