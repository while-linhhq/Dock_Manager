"""
Load YOLO: ưu tiên PyTorch + ultralytics; fallback ONNX (onnxruntime) khi torch bị chặn (WinError 4551).
"""
from __future__ import annotations

import logging
import os
import sys
import threading

logger = logging.getLogger(__name__)

COCO_BOAT_CLASS_ID = 8


def _resolve_onnx_path(model_path: str) -> str | None:
    env = os.getenv("MODEL_ONNX_PATH", "").strip()
    if env and os.path.isfile(env):
        return env
    candidates: list[str] = []
    if model_path.lower().endswith((".pt", ".engine")):
        base = os.path.splitext(model_path)[0] + ".onnx"
        candidates.append(base)
        candidates.append(os.path.join(os.path.dirname(model_path) or ".", os.path.basename(base)))
    # Model đi kèm repo nằm trong models/yolo/ (xem scripts/export_engines.py).
    candidates.append(os.path.join("models", "yolo", "yolo11n.onnx"))
    candidates.append(os.path.join(".", "yolo11n.onnx"))
    for p in candidates:
        if p and os.path.isfile(p):
            return os.path.normpath(p)
    return None


def resolve_yolo_weights(model_path: str) -> tuple[str, str]:
    """
    Chọn file chạy thật: ưu tiên ``.engine`` cùng tên, không có thì dùng ``.pt``.

    Engine TensorRT gắn cứng GPU arch (vd SM86) + phiên bản TensorRT + CUDA nên KHÔNG
    bê sang máy khác được. Vì vậy đây là bước "có thì dùng", không bao giờ báo lỗi —
    máy chưa build engine vẫn chạy bằng .pt bình thường.

    Engine còn phải mở được execution context trên máy này (xem ``engine_usable``); engine
    hỏng thì lùi về .pt thay vì để pipeline chết giữa chừng.

    Trả ``(đường_dẫn, loại)`` với loại ∈ ``{'engine', 'pt'}``.
    """
    try:
        from app.core.config import settings

        prefer_engine = bool(getattr(settings, "YOLO_PREFER_ENGINE", True))
    except Exception:
        prefer_engine = True

    if prefer_engine and model_path.lower().endswith(".pt"):
        candidate = model_path[: -len(".pt")] + ".engine"
        if os.path.isfile(candidate):
            try:
                from app.services.ai.trt_engine import engine_usable

                usable, reason = engine_usable(candidate)
            except Exception as exc:  # noqa: BLE001
                usable, reason = False, str(exc)
            if usable:
                return candidate, "engine"
            print(f"WARNING: engine {candidate} không dùng được ({reason}) → chạy {model_path}")
    return model_path, "pt"


def _torch_loads() -> bool:
    try:
        import torch  # noqa: F401
        return True
    except (OSError, ImportError, RuntimeError):
        return False


class TorchYoloWrapper:
    """Bọc ultralytics YOLO và tự tuần tự hoá lời gọi suy luận.

    `ultralytics.YOLO.predict` không an toàn luồng: mô hình giữ trạng thái, và khi chạy
    `.engine` thì bên trong là một execution context TensorRT. Detector này được dùng chung
    từ nhiều luồng (per-camera, yolo_worker, endpoint test-video), nên khoá đặt ngay tại biên
    module để không phụ thuộc việc từng chỗ gọi có nhớ lấy khoá hay không.
    """

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
        self._lock = threading.Lock()

    def predict_boxes(self, frame):
        with self._lock:
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
    backend_name ∈ {'engine', 'torch', 'onnx'}.
    """
    resolved_path, resolved_kind = resolve_yolo_weights(model_path)
    if resolved_kind == "engine":
        logger.info("YOLO dùng TensorRT engine: %s", resolved_path)

    if _torch_loads():
        from ultralytics import YOLO

        model = YOLO(resolved_path)
        classes = (
            target_classes
            if target_classes is not None
            else resolve_target_classes(model, model_path=resolved_path)
        )
        return (
            TorchYoloWrapper(model, device, conf, classes, imgsz=imgsz),
            "engine" if resolved_kind == "engine" else "torch",
        )

    onnx_path = _resolve_onnx_path(model_path)
    if not onnx_path:
        print(
            "ERROR: Không load được PyTorch (WinError 4551 / ImportError) và không tìm thấy file ONNX.\n"
            "  - Build engine trên máy này:  make engines   (hoặc: python scripts/export_engines.py)\n"
            "  - Hoặc export ONNX trên máy có torch:  yolo export model=models/yolo/yolo26s_finetuned.pt format=onnx\n"
            "  - Đặt file .onnx cạnh MODEL_PATH hoặc set MODEL_ONNX_PATH=... trong .env\n"
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
