"""Chống thoái bộ cho lỗi làm chết backend: dùng chung execution context TensorRT giữa nhiều luồng.

Bối cảnh: `TensorRTModule` giữ MỘT `IExecutionContext` và pipeline gọi nó từ nhiều luồng
(2 luồng camera + luồng visual-id + verifier seam-anchor). Hai luồng cùng vào
`execute_async_v3` trên một context sẽ phá trạng thái graph Myelin của TensorRT; thực tế đã
làm tiến trình backend abort (SIGABRT) — xem `evidence-root-cause-crash.md` trong workspace
SDD và script tái hiện `evidence-repro-trt-race.py`.

Test này không cần GPU: thay execution context bằng bộ ghi biết phát hiện chồng lấn, và thay
đúng hai lời gọi CUDA mà `_run` dùng (`current_stream`, `synchronize`).
"""
from __future__ import annotations

import threading
import time

import pytest
import torch

from app.services.ai.trt_engine import TensorRTModule


class _FakeContext:
    """Execution context giả: đếm số lời gọi `execute_async_v3` đang chạy cùng lúc."""

    def __init__(self, out_dim: int = 4) -> None:
        self.out_dim = out_dim
        self._guard = threading.Lock()
        self._shape: tuple[int, ...] = (1, 3, 8, 8)
        self.active = 0
        self.max_active = 0
        self.calls = 0
        self.overlaps: list[str] = []
        self.batch_mismatch: list[str] = []
        self.thread_batch = threading.local()

    def set_input_shape(self, name: str, shape: tuple[int, ...]) -> bool:
        self._shape = tuple(int(d) for d in shape)
        self.thread_batch.input = self._shape[0]
        return True

    def get_tensor_shape(self, name: str) -> tuple[int, ...]:
        # Cố tình đọc trạng thái dùng chung: nếu hai luồng xen vào nhau, luồng này
        # nhận shape của luồng kia — đúng như TensorRT thật. Chờ một nhịp để cửa sổ
        # race đủ rộng cho test tất định (không phải chờ may rủi).
        time.sleep(0.002)
        batch = self._shape[0]
        self.thread_batch.output = batch
        return (batch, self.out_dim)

    def set_tensor_address(self, name: str, ptr: int) -> None:
        return None

    def execute_async_v3(self, stream: int) -> bool:
        with self._guard:
            self.calls += 1
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            if self.active > 1:
                self.overlaps.append(f'{self.active} lời gọi cùng lúc')
            # Hệ quả thật của race: batch dùng để CẤP PHÁT bộ đệm đầu ra khác batch
            # của dữ liệu đầu vào ⇒ TensorRT ghi quá bộ đệm ⇒ illegal memory access.
            if self.thread_batch.input != self.thread_batch.output:
                self.batch_mismatch.append(
                    f'vào batch={self.thread_batch.input} nhưng cấp phát batch={self.thread_batch.output}'
                )
        time.sleep(0.002)
        with self._guard:
            self.active -= 1
        return True


def _module(ctx: _FakeContext) -> TensorRTModule:
    """TensorRTModule không cần engine thật: chỉ dựng các thuộc tính mà `_run` dùng."""
    module = object.__new__(TensorRTModule)
    module._torch = torch
    module._lock = threading.Lock()  # __init__ thật tạo khoá này
    module._device = torch.device('cpu')
    module._context = ctx
    module._input_name = 'input'
    module._output_name = 'output'
    module._in_dtype = torch.float32
    module._out_dtype = torch.float32
    module._output_dim = ctx.out_dim
    module._min_batch = 1
    module._max_batch = 8
    module._path = 'fake.engine'
    return module


@pytest.fixture(autouse=True)
def _no_cuda(monkeypatch):
    class _Stream:
        cuda_stream = 0

    monkeypatch.setattr(torch.cuda, 'current_stream', lambda *a, **k: _Stream())
    monkeypatch.setattr(torch.cuda, 'synchronize', lambda *a, **k: None)


def test_nhieu_luong_dung_chung_context_khong_chong_lan():
    ctx = _FakeContext()
    module = _module(ctx)
    errors: list[str] = []
    shapes: list[tuple[int, ...]] = []

    def worker(batch: int) -> None:
        for _ in range(15):
            try:
                out = module(torch.zeros(batch, 3, 8, 8))
                shapes.append(tuple(out.shape))
            except Exception as exc:  # noqa: BLE001
                errors.append(f'{type(exc).__name__}: {exc}')

    threads = [threading.Thread(target=worker, args=(1 + i % 3,)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, f'lỗi khi chạy song song: {errors[:3]}'
    assert ctx.calls == 60, f'phải chạy đủ 60 lượt, nhận {ctx.calls}'
    assert ctx.overlaps == [], f'context bị dùng chồng lấn: {ctx.overlaps[:3]}'
    assert ctx.max_active == 1, f'số lời gọi chồng lấn tối đa = {ctx.max_active}'
    assert all(shape[1] == ctx.out_dim for shape in shapes), 'có vector sai chiều'


def test_khong_cap_phat_sai_kich_thuoc_bo_dem_dau_ra():
    """Hệ quả trực tiếp của race: batch dùng để cấp phát bộ đệm khác batch dữ liệu vào.

    Đây chính là cơ chế gây `CUDA error: an illegal memory access` trong production:
    TensorRT ghi kết quả theo shape của luồng khác vào bộ đệm được cấp nhỏ hơn.
    """
    ctx = _FakeContext()
    module = _module(ctx)
    wrong: list[str] = []

    def worker(batch: int) -> None:
        for _ in range(15):
            try:
                out = module(torch.zeros(batch, 3, 8, 8))
                if out.shape[0] != batch:
                    wrong.append(f'xin batch={batch}, nhận {tuple(out.shape)}')
            except Exception as exc:  # noqa: BLE001
                wrong.append(f'xin batch={batch} → {type(exc).__name__}: {exc}')

    threads = [threading.Thread(target=worker, args=(b,)) for b in (1, 3, 1, 3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert wrong == [], f'nhận nhầm shape: {wrong[:3]}'
    assert ctx.batch_mismatch == [], f'cấp phát sai kích thước: {ctx.batch_mismatch[:3]}'
    assert ctx.max_active == 1
