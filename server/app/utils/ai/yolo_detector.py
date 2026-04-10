"""
Load YOLO: ưu tiên PyTorch + ultralytics; fallback ONNX (onnxruntime) khi torch bị chặn (WinError 4551).
"""
from __future__ import annotations

import os
import sys


def _resolve_onnx_path(model_path: str) -> str | None:
    env = os.getenv("MODEL_ONNX_PATH", "").strip()
    if env and os.path.isfile(env):
        return env
    candidates: list[str] = []
    if model_path.lower().endswith(".pt"):
        base = model_path[:-3] + ".onnx"
        candidates.append(base)
        candidates.append(os.path.join(os.path.dirname(model_path) or ".", os.path.basename(base)))
    candidates.append(os.path.join(".", "yolo11n.onnx"))
    for p in candidates:
        if p and os.path.isfile(p):
            return os.path.normpath(p)
    return None


def _torch_loads() -> bool:
    try:
        import torch  # noqa: F401
        return True
    except (OSError, ImportError, RuntimeError):
        return False


class TorchYoloWrapper:
    def __init__(self, model, device: str, conf: float, target_classes: list[int]):
        self.model = model
        self.device = device
        self.conf = conf
        self.target_classes = target_classes

    def predict_boxes(self, frame):
        results = self.model.predict(
            source=frame,
            conf=self.conf,
            classes=self.target_classes,
            verbose=False,
            device=self.device,
        )
        boxes_list = []
        det_confs: list[float] = []
        for r in results:
            for box in r.boxes:
                b = box.xyxy[0].cpu().numpy().astype(int)
                boxes_list.append(b)
                det_confs.append(float(box.conf[0].cpu().item()))
        return boxes_list, det_confs


def load_yolo_detector(
    model_path: str,
    device: str,
    conf: float,
    target_classes: list[int],
):
    """
    Trả (detector, backend_name) với detector có .predict_boxes(frame) -> (boxes_list, det_confs).
    """
    if _torch_loads():
        from ultralytics import YOLO

        model = YOLO(model_path)
        return TorchYoloWrapper(model, device, conf, target_classes), "torch"

    onnx_path = _resolve_onnx_path(model_path)
    if not onnx_path:
        print(
            "ERROR: Không load được PyTorch (WinError 4551 / ImportError) và không tìm thấy file ONNX.\n"
            "  - Export ONNX trên máy có torch:  yolo export model=yolo11n.pt format=onnx\n"
            "  - Đặt yolo11n.onnx cạnh MODEL_PATH hoặc set MODEL_ONNX_PATH=... trong .env\n"
            "  - Hoặc nhờ IT allowlist torch\\lib trong Miniconda (Application Control)."
        )
        sys.exit(1)

    from app.utils.ai.yolo_onnx import OnnxYoloDetector

    print(f"YOLO ONNX fallback (no PyTorch): {onnx_path}")
    return OnnxYoloDetector(onnx_path, conf, target_classes), "onnx"
