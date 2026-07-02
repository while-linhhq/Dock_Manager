import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.ai.ship_id_rule_engine import ShipIdRuleEngine

import cv2

from app.utils.ai.gpu_bootstrap import init_cuda_library_path
from app.utils.ai.paddle_ocr_adapter import (
    _configure_paddle_runtime_env,
    create_paddle_ocr,
    run_ocr_lines,
)

logger = logging.getLogger(__name__)

def _torch_cudnn_blocks_paddle_gpu() -> bool:
    """Torch đã load cuDNN 9.1 (bundled) → Paddle GPU conv sẽ SIGABRT trong cùng process."""
    try:
        import torch

        if not torch.cuda.is_available():
            return False
        version = int(torch.backends.cudnn.version() or 0)
        return version > 0 and version < 90500
    except Exception:
        return False


def _paddle_gpu_probe_subprocess() -> bool:
    """Probe Paddle GPU OCR in an isolated subprocess (same env as OCR worker)."""
    from app.utils.ai.gpu_bootstrap import prepare_paddle_subprocess_env

    server_root = Path(__file__).resolve().parents[3]
    probe_script = """
from app.utils.ai.gpu_bootstrap import init_cuda_library_path
init_cuda_library_path("pre")
import numpy as np
import paddle
if paddle.device.cuda.device_count() <= 0:
    raise SystemExit(1)
paddle.set_device("gpu:0")
from app.utils.ai.paddle_ocr_adapter import create_paddle_ocr, run_ocr_lines
ocr = create_paddle_ocr(lang="en", use_gpu=True, show_log=False)
img = np.zeros((64, 128, 3), dtype=np.uint8)
run_ocr_lines(ocr, img)
"""
    env = os.environ.copy()
    env.update(prepare_paddle_subprocess_env())
    try:
        proc = subprocess.run(
            [sys.executable, '-c', probe_script],
            cwd=str(server_root),
            env=env,
            capture_output=True,
            timeout=120,
            check=False,
        )
    except Exception as exc:
        logger.warning('Paddle GPU subprocess probe error (%s) — CPU OCR', exc)
        return False

    if proc.returncode != 0:
        stderr = (proc.stderr or b'').decode(errors='replace').strip()
        if stderr:
            logger.warning(
                'Paddle GPU subprocess probe failed (rc=%s): %s — CPU OCR',
                proc.returncode,
                stderr[-400:],
            )
        return False
    return True


def _gpu_actually_works() -> bool:
    """Smoke-test Paddle GPU; fallback CPU khi cuDNN torch/paddle không tương thích."""
    if _torch_cudnn_blocks_paddle_gpu():
        logger.warning(
            'Torch cuDNN already loaded (<%s) — Paddle GPU unsafe, using CPU OCR',
            90500,
        )
        return False
    if not _paddle_gpu_probe_subprocess():
        return False
    return True


def create_ship_id_recognizer(
    rule_engine: 'ShipIdRuleEngine | None' = None,
    *,
    prefer_gpu_subprocess: bool = True,
):
    """
    OCR for pipeline: GPU subprocess when torch/cuDNN clash blocks in-process GPU;
    falls back to in-process CPU (legacy stable path).
    """
    use_subprocess = prefer_gpu_subprocess and str(
        os.environ.get('OCR_GPU_SUBPROCESS', '1')
    ).strip().lower() not in ('0', 'false', 'no', 'off')

    if use_subprocess:
        from app.services.ai.ocr_gpu_process import OcrGpuProcessClient

        client = OcrGpuProcessClient()
        if client.start():
            return client
        client.close()
        logger.warning('OCR GPU subprocess unavailable — in-process CPU')

    return ShipIdRecognizer(rule_engine=rule_engine, use_gpu=False)


class ShipIdRecognizer:
    def __init__(
        self,
        lang="en",
        use_gpu=None,
        show_log=False,
        rule_engine=None,
        *,
        assume_gpu_available: bool = False,
    ):
        """Khởi tạo PaddleOCR; auto fallback CPU nếu GPU/cuDNN không sẵn sàng."""
        _configure_paddle_runtime_env()
        init_cuda_library_path('pre')
        import paddle

        if use_gpu is None:
            use_gpu = (
                assume_gpu_available and paddle.device.cuda.device_count() > 0
            ) or _gpu_actually_works()
        elif use_gpu:
            if assume_gpu_available and paddle.device.cuda.device_count() > 0:
                pass
            elif not _gpu_actually_works():
                use_gpu = False

        paddle.set_device('gpu:0' if use_gpu else 'cpu')
        init_cuda_library_path('post')

        self._use_gpu = bool(use_gpu)
        self.ocr = create_paddle_ocr(lang=lang, use_gpu=use_gpu, show_log=show_log)
        logger.info('ShipIdRecognizer initialized (device=%s)', 'gpu' if use_gpu else 'cpu')
        self.pattern = r"([A-Z50]{2})[-\s]?(\d{4})"
        self._rule_engine = rule_engine  # ShipIdRuleEngine | None
        # CLAHE second pass only runs when the raw pass is empty or below this
        # confidence. Skipping it on clear crops (the majority) roughly halves
        # OCR CPU cost. Tune via env; set <=0 to always run both passes.
        try:
            self._second_pass_conf_threshold = float(
                os.environ.get('OCR_SECOND_PASS_CONF_THRESHOLD', '0.85')
            )
        except ValueError:
            self._second_pass_conf_threshold = 0.85

    def close(self) -> None:
        """No-op for in-process recognizer; subprocess client overrides."""
        return None

    @staticmethod
    def _ensure_min_side_bgr(img_bgr, min_side: int = 480):
        """Crop nhỏ khiến PP-OCR det/rec hay trả None hoặc bị lọc; upscale trước khi OCR."""
        if img_bgr is None or img_bgr.size == 0:
            return img_bgr
        h, w = img_bgr.shape[:2]
        m = min(h, w)
        if m >= min_side or m <= 0:
            return img_bgr
        scale = min_side / m
        return cv2.resize(
            img_bgr,
            (int(round(w * scale)), int(round(h * scale))),
            interpolation=cv2.INTER_CUBIC,
        )

    def preprocess(self, img_bgr):
        """
        Tiền xử lý ảnh: upscale nếu crop nhỏ (Paddle det hay trả None / drop ở kích thước gốc),
        rồi Grayscale + CLAHE. Không dùng Otsu nhị phân — dễ làm méo chữ số (vd. 6/5).
        """
        img_bgr = self._ensure_min_side_bgr(img_bgr)
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        return clahe.apply(gray)

    def extract_ship_id(self, ocr_results):
        """
        Filter ship IDs from OCR results.
        Delegates to rule engine when available; falls back to hardcoded pattern.
        """
        found_ids = []
        for line in ocr_results:
            # PaddleOCR 2.7 format: [[box], (text, conf)]
            if not line or len(line) < 2:
                continue
            text, prob = line[1]
            clean_text = text.upper().strip().replace(' ', '')

            if self._rule_engine is not None:
                candidates = self._rule_engine.extract_ship_ids(clean_text)
                for c in candidates:
                    found_ids.append({
                        'id': c['id'],
                        'confidence': float(prob),
                        'raw_text': text,
                    })
            else:
                match = re.search(self.pattern, clean_text)
                if match:
                    prefix = match.group(1).replace('5', 'S').replace('0', 'O')
                    number = match.group(2)
                    final_id = f'{prefix}-{number}'
                    found_ids.append({
                        'id': final_id,
                        'confidence': float(prob),
                        'raw_text': text,
                    })
        return found_ids

    @staticmethod
    def _dedupe_by_confidence(ship_ids):
        """Sắp xếp theo confidence, giữ bản có confidence cao nhất mỗi id."""
        if not ship_ids:
            return []
        ship_ids.sort(key=lambda x: x["confidence"], reverse=True)
        unique_ids = {}
        for item in ship_ids:
            sid = item["id"]
            if sid not in unique_ids or item["confidence"] > unique_ids[sid]["confidence"]:
                unique_ids[sid] = item
        return list(unique_ids.values())

    def recognize_bgr(self, img_bgr):
        """
        Nhận dạng mã tàu từ ảnh BGR (crop).

        Chạy OCR trên ảnh gốc trước. Chỉ chạy pass thứ 2 (CLAHE, nặng CPU) khi
        pass đầu không ra mã hoặc confidence dưới ngưỡng — crop rõ (đa số) chỉ
        tốn 1 lần OCR, giảm ~1/2 tải CPU của OCR.
        """
        if img_bgr is None or img_bgr.size == 0:
            return []

        # 1. OCR trên ảnh gốc (cùng upscale tối thiểu như preprocess)
        first_lines = run_ocr_lines(self.ocr, self._ensure_min_side_bgr(img_bgr))
        first_ids = self.extract_ship_id(first_lines)

        # Early-exit khi pass đầu đã cho kết quả đủ tin cậy → bỏ pass CLAHE.
        threshold = self._second_pass_conf_threshold
        if threshold > 0 and first_ids:
            best_conf = max(item["confidence"] for item in first_ids)
            if best_conf >= threshold:
                return self._dedupe_by_confidence(first_ids)

        # 2. OCR trên ảnh tiền xử lý (CLAHE) — chỉ khi pass đầu yếu/không có.
        processed = self.preprocess(img_bgr)
        processed_bgr = cv2.cvtColor(processed, cv2.COLOR_GRAY2BGR)
        second_ids = self.extract_ship_id(run_ocr_lines(self.ocr, processed_bgr))

        return self._dedupe_by_confidence(first_ids + second_ids)
