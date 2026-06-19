"""
Load YOLO: ưu tiên PyTorch + ultralytics; fallback ONNX (onnxruntime) khi torch bị chặn (WinError 4551).
"""
from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger(__name__)

COCO_BOAT_CLASS_ID = 8


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
    def __init__(
        self,
        model,
        device: str,
        conf: float,
        target_classes: list[int],
        *,
        imgsz: int = 640,
    ):
        self.model = model
        self.device = device
        self.conf = conf
        self.target_classes = target_classes
        self.imgsz = max(32, int(imgsz))

    def predict_boxes(self, frame):
        results = self.model.predict(
            source=frame,
            conf=self.conf,
            classes=self.target_classes,
            imgsz=self.imgsz,
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


def resolve_target_classes(model, *, model_path: str = '') -> list[int]:
    """
  Resolve YOLO `classes=` filter from model metadata.
  Fine-tuned single-class boat models use id 0; COCO pretrained uses id 8.
    """
    names = getattr(model, 'names', None) or {}
    if isinstance(names, dict) and names:
        if len(names) == 1:
            return [int(next(iter(names.keys())))]
        boat_ids = [int(k) for k, v in names.items() if str(v).lower() == 'boat']
        if boat_ids:
            return boat_ids

    path_hint = os.path.basename(model_path).lower()
    if 'finetuned' in path_hint or 'fine-tune' in path_hint:
        return [0]

    return [COCO_BOAT_CLASS_ID]


def load_yolo_detector(
    model_path: str,
    device: str,
    conf: float,
    target_classes: list[int] | None = None,
    *,
    imgsz: int = 640,
):
    """
    Trả (detector, backend_name) với detector có .predict_boxes(frame) -> (boxes_list, det_confs).
    """
    if _torch_loads():
        from ultralytics import YOLO

        model = YOLO(model_path)
        classes = (
            target_classes
            if target_classes is not None
            else resolve_target_classes(model, model_path=model_path)
        )
        return (
            TorchYoloWrapper(model, device, conf, classes, imgsz=imgsz),
            'torch',
        )

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

    classes = target_classes if target_classes is not None else resolve_target_classes(
        None,
        model_path=model_path,
    )
    print(f'YOLO ONNX fallback (no PyTorch): {onnx_path}')
    return OnnxYoloDetector(onnx_path, conf, classes), 'onnx'
