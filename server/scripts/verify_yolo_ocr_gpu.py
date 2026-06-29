"""Smoke: YOLO GPU + OCR (subprocess GPU) after torch is loaded."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

import torch
from ultralytics import YOLO

from app.core.config import settings
from app.services.ai.ship_id_rule_engine import get_rule_engine
from app.utils.ai.ship_id_recognizer import create_ship_id_recognizer


def main() -> int:
    assert torch.cuda.is_available(), 'torch CUDA required'
    print('torch', torch.__version__, torch.cuda.get_device_name(0))

    model = YOLO(str(settings.MODEL_PATH))
    yolo_res = model.predict(np.zeros((640, 640, 3), dtype=np.uint8), device=0, verbose=False)
    print('yolo predict ok', len(yolo_res[0].boxes) if yolo_res else 0)

    recognizer = create_ship_id_recognizer(rule_engine=get_rule_engine())
    device = getattr(recognizer, 'device', 'in-process')
    print('ocr device', device)

    crop = np.random.randint(0, 255, (200, 400, 3), dtype=np.uint8)
    result = recognizer.recognize_bgr(crop)
    print('ocr recognize ok', len(result), 'hits')

    recognizer.close()
    if device != 'gpu':
        print('WARN: OCR not on GPU subprocess — check prepare_paddle_subprocess_env')
        return 1
    print('PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
