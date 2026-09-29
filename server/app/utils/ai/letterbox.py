"""Letterbox thuần bằng OpenCV, khớp hình học của `ultralytics.utils.ops.LetterBox`.

Dùng để chạy CLAHE ở **kích thước detector** thay vì full-res: ảnh được resize về vừa
`imgsz` trước, tiền xử lý ở đó, rồi mới pad viền xám cho đủ canvas vuông mà model cần.
Áp dụng lại lên một ảnh đã đúng kích thước là no-op trong ultralytics, nên box trả về
nằm ở hệ của ảnh đã letterbox — `unletterbox_boxes` đưa chúng về toạ độ frame gốc.

Hình học phải giữ đúng như ultralytics (xem `LetterBox.__call__` và `ops.scale_boxes`):
`scaleup=True`, pad căn giữa ``int(round(d/2 - 0.1))`` / ``int(round(d/2 + 0.1))``,
nội suy ``INTER_LINEAR``, viền xám 114.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

#: Giá trị viền xám mà ultralytics dùng khi pad ảnh cho model.
PAD_VALUE = 114


@dataclass(frozen=True)
class Letterbox:
    """Kết quả letterbox: nội dung đã resize (chưa pad) + tham số quy đổi toạ độ."""

    content: np.ndarray
    scale: float
    pad_x: int
    pad_y: int
    size: int

    def padded(self, image: np.ndarray | None = None, pad_value: int = PAD_VALUE) -> np.ndarray:
        """Pad `image` (mặc định chính `content`) thành canvas vuông `size × size`."""
        source = self.content if image is None else image
        if source.shape[:2] != self.content.shape[:2]:
            raise ValueError(
                f'Ảnh phải cùng kích thước nội dung {self.content.shape[:2]}, nhận {source.shape[:2]}'
            )
        bottom = self.size - source.shape[0] - self.pad_y
        right = self.size - source.shape[1] - self.pad_x
        return cv2.copyMakeBorder(
            source,
            self.pad_y,
            max(bottom, 0),
            self.pad_x,
            max(right, 0),
            cv2.BORDER_CONSTANT,
            value=(pad_value,) * 3,
        )


def letterbox_frame(frame: np.ndarray, imgsz: int) -> Letterbox:
    """Resize `frame` về vừa `imgsz` (giữ tỉ lệ) và tính pad căn giữa như ultralytics."""
    if frame.ndim != 3 or frame.shape[0] <= 0 or frame.shape[1] <= 0:
        raise ValueError(f'Frame không hợp lệ: shape={getattr(frame, "shape", None)}')
    if imgsz <= 0:
        raise ValueError(f'imgsz không hợp lệ: {imgsz}')

    height, width = frame.shape[:2]
    scale = min(imgsz / height, imgsz / width)
    new_width = int(round(width * scale))
    new_height = int(round(height * scale))
    content = (
        cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_LINEAR)
        if (new_width, new_height) != (width, height)
        else frame
    )
    pad_x = int(round((imgsz - new_width) / 2 - 0.1))
    pad_y = int(round((imgsz - new_height) / 2 - 0.1))
    return Letterbox(content=content, scale=scale, pad_x=pad_x, pad_y=pad_y, size=imgsz)


def unletterbox_boxes(
    boxes: np.ndarray | list,
    scale: float,
    pad_x: int,
    pad_y: int,
    *,
    width: int | None = None,
    height: int | None = None,
) -> np.ndarray:
    """Đưa box từ hệ ảnh đã letterbox về hệ frame gốc (trừ pad, chia tỉ lệ).

    Truyền `width`/`height` của frame gốc để kẹp box vào biên ảnh, giống
    `ultralytics.utils.ops.scale_boxes` — nhờ vậy box vào tracker trùng đường cũ.
    """
    array = np.asarray(boxes, dtype=np.float32).reshape(-1, 4)
    if array.size == 0:
        return np.zeros((0, 4), dtype=np.float32)
    if scale <= 0:
        raise ValueError(f'scale không hợp lệ: {scale}')
    out = array.copy()
    out[:, [0, 2]] = (out[:, [0, 2]] - float(pad_x)) / float(scale)
    out[:, [1, 3]] = (out[:, [1, 3]] - float(pad_y)) / float(scale)
    if width is not None and height is not None:
        out[:, [0, 2]] = np.clip(out[:, [0, 2]], 0.0, float(width))
        out[:, [1, 3]] = np.clip(out[:, [1, 3]], 0.0, float(height))
    return out
