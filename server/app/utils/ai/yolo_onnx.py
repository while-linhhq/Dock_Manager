"""
YOLOv8 ONNX inference qua onnxruntime — không cần PyTorch/ultralytics.
Dùng khi Windows Application Control chặn torch_python.dll (WinError 4551).

Cần file ONNX export từ Ultralytics, ví dụ:
  yolo export model=yolo11n.pt format=onnx
"""
from __future__ import annotations

import cv2
import numpy as np
import onnxruntime as ort


def _letterbox(
    img: np.ndarray,
    new_shape: tuple[int, int],
) -> tuple[np.ndarray, tuple[int, int], tuple[int, int]]:
    """Resize + pad; trả (img_640, (top, left), (orig_h, orig_w))."""
    shape = img.shape[:2]  # h, w
    new_h, new_w = new_shape
    r = min(new_h / shape[0], new_w / shape[1])
    new_unpad = (int(round(shape[1] * r)), int(round(shape[0] * r)))
    dw, dh = (new_w - new_unpad[0]) / 2, (new_h - new_unpad[1]) / 2
    if shape[::-1] != new_unpad:
        img = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)
    top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
    left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
    img = cv2.copyMakeBorder(
        img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(114, 114, 114)
    )
    return img, (top, left), (shape[0], shape[1])


class OnnxYoloDetector:
    """Wrapper tương thích với TorchYoloWrapper.predict_boxes."""

    def __init__(
        self,
        onnx_path: str,
        conf: float,
        target_classes: list[int],
        iou_thres: float = 0.45,
    ):
        self.conf = conf
        self.target_classes = set(target_classes)
        self.iou_thres = iou_thres

        available = ort.get_available_providers()
        preferred = []
        for p in ("CUDAExecutionProvider", "DmlExecutionProvider", "CPUExecutionProvider"):
            if p in available:
                preferred.append(p)
        if not preferred:
            preferred = available
        self.session = ort.InferenceSession(onnx_path, providers=preferred)
        inp = self.session.get_inputs()[0]
        self.input_name = inp.name
        shp = inp.shape
        self.input_height = int(shp[2]) if isinstance(shp[2], int) else 640
        self.input_width = int(shp[3]) if isinstance(shp[3], int) else 640

    def predict_boxes(self, frame: np.ndarray) -> tuple[list, list[float]]:
        """
        frame: BGR uint8.
        Trả về (boxes_list, det_confs) — boxes là ndarray int xyxy như ultralytics.
        """
        orig_h, orig_w = frame.shape[:2]
        img_lb, pad, _ = _letterbox(
            frame, (self.input_height, self.input_width)
        )
        img_rgb = cv2.cvtColor(img_lb, cv2.COLOR_BGR2RGB)
        image_data = np.transpose(img_rgb, (2, 0, 1)).astype(np.float32) / 255.0
        image_data = np.expand_dims(image_data, 0)

        outputs = self.session.run(None, {self.input_name: image_data})
        # Giống examples/YOLOv8-ONNXRuntime/main.py: [1, 84, 8400] -> [8400, 84]
        out = outputs[0]
        outputs_t = np.transpose(np.squeeze(out)).copy()
        outputs_t[:, 0] -= pad[1]
        outputs_t[:, 1] -= pad[0]

        gain = min(
            self.input_height / orig_h,
            self.input_width / orig_w,
        )

        boxes_xywh = []
        scores = []
        class_ids = []

        for i in range(outputs_t.shape[0]):
            row = outputs_t[i]
            classes_scores = row[4:]
            max_score = float(np.amax(classes_scores))
            if max_score < self.conf:
                continue
            class_id = int(np.argmax(classes_scores))
            if class_id not in self.target_classes:
                continue

            x, y, w, h = row[0], row[1], row[2], row[3]
            left = (x - w / 2) / gain
            top = (y - h / 2) / gain
            width = w / gain
            height = h / gain
            boxes_xywh.append([left, top, width, height])
            scores.append(max_score)
            class_ids.append(class_id)

        if not boxes_xywh:
            return [], []

        indices = cv2.dnn.NMSBoxes(
            boxes_xywh, scores, self.conf, self.iou_thres
        )
        if indices is None:
            return [], []
        idx_arr = np.array(indices).flatten()
        if idx_arr.size == 0:
            return [], []

        boxes_list = []
        det_confs: list[float] = []
        for j in idx_arr:
            j = int(j)
            bx, by, bw, bh = boxes_xywh[j]
            x1 = max(0, int(bx))
            y1 = max(0, int(by))
            x2 = min(orig_w, int(bx + bw))
            y2 = min(orig_h, int(by + bh))
            if x2 <= x1 or y2 <= y1:
                continue
            boxes_list.append(np.array([x1, y1, x2, y2], dtype=np.int32))
            det_confs.append(scores[j])

        return boxes_list, det_confs
