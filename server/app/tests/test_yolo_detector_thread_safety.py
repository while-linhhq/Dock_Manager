"""Chống thoái bộ cho lỗi cùng lớp với crash TensorRT: detector YOLO dùng chung giữa các luồng.

`TorchYoloWrapper` bọc `ultralytics.YOLO.predict`, vốn không an toàn luồng (mô hình giữ trạng
thái, và khi chạy `.engine` thì bên trong là một execution context TensorRT). Detector này được
gọi từ nhiều nơi: luồng per-camera, `yolo_worker`, và `pipeline_service.test_video_sync` (endpoint
`POST /pipeline/test-video`) — chỗ gọi cuối cùng không hề lấy khoá. Thay vì trông chờ từng chỗ gọi
nhớ khoá, lớp bọc tự tuần tự hoá; test này khoá chặt hành vi đó.

Không cần GPU: mô hình được thay bằng bộ ghi biết phát hiện chồng lấn.
"""
from __future__ import annotations

import threading
import time

import numpy as np
import pytest

from app.utils.ai.yolo_detector import TorchYoloWrapper


class _FakeYoloModel:
    """Mô hình giả: đếm số lời gọi `predict` đang chạy cùng lúc."""

    def __init__(self, results: list | None = None) -> None:
        self._guard = threading.Lock()
        self.active = 0
        self.max_active = 0
        self.calls = 0
        self.overlaps: list[str] = []
        self.results = results if results is not None else []

    def predict(self, **kwargs):
        with self._guard:
            self.calls += 1
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            if self.active > 1:
                self.overlaps.append(f'{self.active} lời gọi cùng lúc')
        time.sleep(0.002)  # mở rộng cửa sổ để race lộ ra
        with self._guard:
            self.active -= 1
        return self.results


def test_torch_yolo_wrapper_tuan_tu_hoa_predict_khi_nhieu_luong():
    model = _FakeYoloModel()
    wrapper = TorchYoloWrapper(model, 'cpu', 0.25, [0])
    frame = np.zeros((8, 8, 3), dtype=np.uint8)
    errors: list[str] = []

    def worker() -> None:
        for _ in range(15):
            try:
                boxes, confs = wrapper.predict_boxes(frame)
                if boxes != [] or confs != []:
                    errors.append(f'kết quả sai: {boxes!r} {confs!r}')
            except Exception as exc:  # noqa: BLE001
                errors.append(f'{type(exc).__name__}: {exc}')

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, f'lỗi khi chạy song song: {errors[:3]}'
    assert model.calls == 60, f'phải chạy đủ 60 lượt, nhận {model.calls}'
    assert model.overlaps == [], f'YOLO bị gọi chồng lấn: {model.overlaps[:3]}'
    assert model.max_active == 1, f'số lời gọi chồng lấn tối đa = {model.max_active}'


class _FakeOrtSession:
    """Phiên onnxruntime giả: đếm số lời gọi `run` đang chạy cùng lúc."""

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self.active = 0
        self.max_active = 0
        self.calls = 0
        self.overlaps: list[str] = []

    def run(self, output_names, input_feed):
        with self._guard:
            self.calls += 1
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            if self.active > 1:
                self.overlaps.append(f'{self.active} lời gọi cùng lúc')
        time.sleep(0.002)
        with self._guard:
            self.active -= 1
        return [np.zeros((1, 84, 100), dtype=np.float32)]


def _onnx_detector(session):
    pytest.importorskip('onnxruntime')
    from app.utils.ai.yolo_onnx import OnnxYoloDetector

    detector = object.__new__(OnnxYoloDetector)
    detector.conf = 0.25
    detector.target_classes = {0}
    detector.iou_thres = 0.45
    detector.session = session
    detector._lock = threading.Lock()  # __init__ thật tạo khoá này
    detector.input_name = 'images'
    detector.input_height = 64
    detector.input_width = 64
    return detector


def test_onnx_detector_tuan_tu_hoa_session_run_khi_nhieu_luong():
    """Đường ONNX (fallback khi torch bị chặn) cũng phải tuần tự hoá như đường torch.

    Chưa tìm được dẫn chứng văn bản nào khẳng định `InferenceSession.run` an toàn luồng,
    nên lớp bọc tự bảo đảm thay vì dựa vào giả định.
    """
    session = _FakeOrtSession()
    detector = _onnx_detector(session)
    frame = np.zeros((48, 64, 3), dtype=np.uint8)
    errors: list[str] = []

    def worker() -> None:
        for _ in range(15):
            try:
                boxes, confs = detector.predict_boxes(frame)
                if boxes != [] or confs != []:
                    errors.append(f'kết quả sai: {boxes!r} {confs!r}')
            except Exception as exc:  # noqa: BLE001
                errors.append(f'{type(exc).__name__}: {exc}')

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, f'lỗi khi chạy song song: {errors[:3]}'
    assert session.calls == 60, f'phải chạy đủ 60 lượt, nhận {session.calls}'
    assert session.overlaps == [], f'phiên ONNX bị gọi chồng lấn: {session.overlaps[:3]}'
    assert session.max_active == 1, f'số lời gọi chồng lấn tối đa = {session.max_active}'
