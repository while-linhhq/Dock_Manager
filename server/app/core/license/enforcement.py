"""Enforcement license ở tầng nghiệp vụ (Keygate).

Gồm quota camera và gate bắt đầu pipeline mới. Quota camera đếm TOÀN BỘ row
trong bảng ``cameras`` — kể cả camera đang tắt — theo đúng hợp đồng với
Keygate: tạo camera tiêu tốn slot, xoá camera giải phóng slot. Vì vậy chỉ
``create_camera`` bị chặn, không chặn update/delete.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.license.service import license_service
from app.repositories.camera_repository import camera_repo

logger = logging.getLogger(__name__)

_LICENSE_BLOCKED_CAMERA_DETAIL = (
    'License không hợp lệ hoặc đã hết hạn. Không thể tạo camera mới; '
    'dữ liệu hiện có vẫn giữ nguyên.'
)


class CameraLimitExceeded(Exception):
    """License không cho tạo thêm camera vì đã đạt ``limit``."""

    limit: int
    current: int

    def __init__(self, limit: int, current: int):
        self.limit = int(limit)
        self.current = int(current)
        super().__init__(f'camera quota exceeded: {self.current}/{self.limit}')


def check_camera_quota(db: Session) -> None:
    """Chặn tạo camera mới khi license không dùng được hoặc đã đạt quota.

    Thứ tự: license không usable (enforce) → 403 license; sau đó mới kiểm tra
    ``max_cameras``. Trả về bình thường khi còn slot hoặc mode ``warn``/``off``;
    chỉ raise :class:`CameraLimitExceeded` khi mode ``enforce`` và đã đầy.
    """
    if license_service.should_block_new_behavior():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_LICENSE_BLOCKED_CAMERA_DETAIL,
        )

    limit = license_service.max_cameras()
    mode = license_service.enforcement_mode()
    current = camera_repo.count_all(db)
    if current < limit:
        return
    if mode == 'enforce':
        raise CameraLimitExceeded(limit, current)
    if mode == 'warn':
        logger.warning('license camera quota exceeded: %s/%s (warn mode)', current, limit)
        return
    # mode 'off' -> không chặn (service đã chuẩn hoá mode trước khi trả về).


def camera_quota_snapshot(db: Session) -> tuple[int, int]:
    """Trả ``(current, limit)`` để UI hiển thị mức dùng quota camera."""
    return camera_repo.count_all(db), license_service.max_cameras()


def enforce_pipeline_start() -> None:
    """Chặn bắt đầu pipeline MỚI khi license không dùng được (mode ``enforce``).

    Chỉ gọi ở luồng start; pipeline đang chạy vẫn tiếp tục (stop/status/logs
    không bị ảnh hưởng).
    """
    if license_service.should_block_new_behavior():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                'License không hợp lệ hoặc đã hết hạn. Không thể bắt đầu pipeline mới; '
                'pipeline đang chạy vẫn tiếp tục.'
            ),
        )
