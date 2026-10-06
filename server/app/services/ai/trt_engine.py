"""Chạy model TensorRT (.engine) như một nn.Module tối giản.

Vì sao cần lớp này: các extractor hiện gọi ``model(tensor)`` và đọc ``num_features``.
Engine TensorRT không phải nn.Module, nên bọc lại thành object có cùng giao diện để
phần tiền xử lý / hậu xử lý phía sau không phải đổi gì.

Bộ nhớ vào/ra cấp phát bằng ``torch.empty`` trên CUDA rồi truyền ``data_ptr()`` cho
TensorRT (API ``set_tensor_address`` + ``execute_async_v3``). Nhờ vậy KHÔNG cần pycuda
(không cần nvcc/CUDA toolkit để biên dịch) — chỉ cần gói ``tensorrt`` và torch.
"""
from __future__ import annotations

import logging
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_NUMPY_TO_TORCH: dict[str, str] = {
    'float16': 'float16',
    'float32': 'float32',
    'float64': 'float64',
    'int8': 'int8',
    'int32': 'int32',
    'int64': 'int64',
    'bool': 'bool',
}


@lru_cache(maxsize=8)
def engine_usable(engine_path: str) -> tuple[bool, str]:
    """Engine có deserialize + tạo được execution context không.

    Phải kiểm tra trước khi chọn engine: TensorRT từ chối tạo context khi môi trường lúc
    chạy khác lúc build. Thực tế đã gặp — ``import paddle`` đặt ``NVIDIA_TF32_OVERRIDE=0``,
    engine build lúc biến này chưa có sẽ hỏng (Myelin: "Inconsistent setting of
    NVIDIA_TF32_OVERRIDE"). Hỏng thì lùi về .pt chứ không làm chết pipeline.
    """
    path = Path(engine_path)
    if not path.is_file():
        return False, 'không thấy file'
    try:
        import tensorrt as trt
    except Exception as exc:  # noqa: BLE001
        return False, f'chưa cài TensorRT ({exc})'

    try:
        runtime = trt.Runtime(trt.Logger(trt.Logger.ERROR))
        engine = runtime.deserialize_cuda_engine(_engine_bytes(path))
        if engine is None:
            return False, 'deserialize thất bại'
        if engine.create_execution_context() is None:
            return False, 'không tạo được execution context (lệch NVIDIA_TF32_OVERRIDE lúc build/chạy)'
        return True, 'ok'
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:200]


def _engine_bytes(path: Path) -> bytes:
    """Đọc engine, bỏ phần metadata mà ultralytics ghi kèm ở đầu file.

    Ultralytics lưu ``<4 byte độ dài><JSON metadata>`` rồi mới tới phần engine ("ftrt"…).
    Loader của ultralytics tự bỏ qua, còn TensorRT thuần thì báo
    ``header.magicTag == kEXPECTED_MAGIC_TAG failed``.
    """
    data = path.read_bytes()
    if data[:4] == b'ftrt':
        return data
    length = int.from_bytes(data[:4], 'little')
    if 0 < length < len(data) - 4 and data[4:5] == b'{' and data[4 + length : 4 + length + 4] == b'ftrt':
        return data[4 + length :]
    return data


def tensorrt_available() -> bool:
    try:
        import tensorrt  # noqa: F401

        return True
    except Exception:
        return False


class TensorRTModule:
    """Giao diện giống nn.Module cho một engine TensorRT.

    Chỉ hỗ trợ 1 input + 1 output (đúng nhu cầu của các backbone trong dự án).
    Batch động trong khoảng optimization profile của engine; batch lớn hơn hoặc
    engine cố định batch khác sẽ được tự động chia nhỏ và ghép lại.

    An toàn luồng: TensorRT KHÔNG bảo đảm an toàn luồng cho execution context. Pipeline
    gọi cùng một extractor từ nhiều luồng (2 luồng camera + luồng visual-id + verifier
    seam-anchor), nên mọi thao tác trên context được tuần tự hoá bằng ``_lock``. Không có
    khoá này, hai luồng cùng đổi input shape rồi cùng execute sẽ phá graph Myelin và/hoặc
    làm luồng này cấp phát bộ đệm theo shape của luồng kia — TensorRT ghi quá bộ đệm và
    tiến trình backend abort (SIGABRT). Xem test:
    ``app/tests/test_trt_engine_thread_safety.py``.
    """

    def __init__(
        self,
        engine_path: str | Path,
        *,
        device: int | str = 0,
        output_dim: int | None = None,
    ) -> None:
        import tensorrt as trt
        import torch

        path = Path(engine_path)
        if not path.is_file():
            raise FileNotFoundError(f'Không thấy engine TensorRT: {path}')

        self._torch = torch
        self._lock = threading.Lock()
        self._device = torch.device(f'cuda:{device}' if str(device).isdigit() else str(device))
        self._logger = trt.Logger(trt.Logger.WARNING)
        self._runtime = trt.Runtime(self._logger)
        self._engine = self._runtime.deserialize_cuda_engine(_engine_bytes(path))
        if self._engine is None:
            raise RuntimeError(f'TensorRT không deserialize được engine: {path}')
        self._context = self._engine.create_execution_context()
        if self._context is None:
            raise RuntimeError(
                f'TensorRT không tạo được execution context cho {path} '
                '(thường do NVIDIA_TF32_OVERRIDE lúc build khác lúc chạy — build lại: make engines)'
            )

        inputs: list[str] = []
        outputs: list[str] = []
        for index in range(self._engine.num_io_tensors):
            name = self._engine.get_tensor_name(index)
            if self._engine.get_tensor_mode(name) == trt.TensorIOMode.INPUT:
                inputs.append(name)
            else:
                outputs.append(name)
        if len(inputs) != 1 or len(outputs) != 1:
            raise RuntimeError(
                f'Engine phải có đúng 1 input + 1 output, nhận được {inputs} / {outputs}'
            )

        self._input_name = inputs[0]
        self._output_name = outputs[0]
        self._in_dtype = self._torch_dtype(trt, self._engine.get_tensor_dtype(self._input_name))
        self._out_dtype = self._torch_dtype(trt, self._engine.get_tensor_dtype(self._output_name))

        profile_min, _, profile_max = self._engine.get_tensor_profile_shape(self._input_name, 0)
        self._min_batch = max(1, int(profile_min[0]))
        self._max_batch = max(1, int(profile_max[0]))

        static_shape = tuple(int(d) for d in self._engine.get_tensor_shape(self._output_name))
        self._static_output_dim = static_shape[-1] if all(d > 0 for d in static_shape) else None
        self._output_dim = int(output_dim or self._static_output_dim or 0)
        self._path = str(path)

    @staticmethod
    def _torch_dtype(trt: Any, dtype: Any) -> Any:
        import torch

        name = _NUMPY_TO_TORCH.get(str(trt.nptype(dtype).__name__))
        if not name:
            raise RuntimeError(f'Kiểu dữ liệu TensorRT không hỗ trợ: {dtype}')
        return getattr(torch, name)

    # --- giao diện giống nn.Module -------------------------------------------------
    @property
    def num_features(self) -> int:
        return self._output_dim

    @property
    def engine_path(self) -> str:
        return self._path

    @property
    def max_batch(self) -> int:
        return self._max_batch

    def eval(self) -> 'TensorRTModule':
        return self

    def to(self, device: Any = None) -> 'TensorRTModule':  # noqa: ARG002 - engine gắn cứng device
        return self

    def __call__(self, tensor: Any) -> Any:
        torch = self._torch
        if tensor.ndim == 3:
            tensor = tensor.unsqueeze(0)
        batch = int(tensor.shape[0])
        if batch <= self._max_batch and batch >= self._min_batch:
            return self._run(tensor)

        # Batch nằm ngoài profile: chạy từng phần rồi ghép lại.
        outputs = []
        step = max(1, self._max_batch)
        for start in range(0, batch, step):
            outputs.append(self._run(tensor[start : start + step]))
        return torch.cat(outputs, dim=0)

    def _run(self, tensor: Any) -> Any:
        torch = self._torch
        data = tensor.to(device=self._device, dtype=self._in_dtype).contiguous()

        # Toàn bộ thao tác trên execution context phải nằm trong khoá: context là tài
        # nguyên dùng chung, không an toàn luồng (xem docstring của lớp).
        with self._lock:
            if not self._context.set_input_shape(self._input_name, tuple(data.shape)):
                raise RuntimeError(
                    f'Engine không nhận shape {tuple(data.shape)} '
                    f'(batch cho phép {self._min_batch}..{self._max_batch})'
                )

            out_shape = tuple(int(d) for d in self._context.get_tensor_shape(self._output_name))
            output = torch.empty(out_shape, dtype=self._out_dtype, device=self._device)

            self._context.set_tensor_address(self._input_name, data.data_ptr())
            self._context.set_tensor_address(self._output_name, output.data_ptr())
            if not self._context.execute_async_v3(torch.cuda.current_stream().cuda_stream):
                raise RuntimeError('TensorRT execute_async_v3 thất bại')
            torch.cuda.synchronize()

            if self._output_dim <= 0 and output.numel():
                self._output_dim = int(output.reshape(int(data.shape[0]), -1).shape[-1])
        return output.reshape(int(data.shape[0]), -1).to(torch.float32)
