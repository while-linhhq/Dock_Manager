"""Enforcement license ở tầng nghiệp vụ (Keygate).

Quota camera đếm TOÀN BỘ row trong bảng ``cameras`` — kể cả camera đang tắt —
theo đúng hợp đồng với Keygate: tạo camera tiêu tốn slot, xoá camera giải
phóng slot. Vì vậy chỉ ``create_camera`` bị chặn, không chặn update/delete.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.core.license.service import license_service
from app.repositories.camera_repository import camera_repo

logger = logging.getLogger(__name__)


class CameraLimitExceeded(Exception):
    """License không cho tạo thêm camera vì đã đạt ``limit``."""

    limit: int
    current: int

    def __init__(self, limit: int, current: int):
        self.limit = int(limit)
        self.current = int(current)
        super().__init__(f'camera quota exceeded: {self.current}/{self.limit}')


def check_camera_quota(db: Session) -> None:
    """Chặn tạo camera mới khi đã đạt ``max_cameras`` của license.

    Trả về bình thường khi còn slot hoặc enforcement mode là ``warn``/``off``;
    chỉ raise :class:`CameraLimitExceeded` khi mode ``enforce`` và đã đầy.
    """
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
