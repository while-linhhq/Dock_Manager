"""Mã máy (hardware fingerprint) — chống copy bộ cài DSight.

Mã máy được tính từ các định danh phần cứng đọc qua bind mount read-only
(``/host/...`` trong docker-compose): ``/etc/machine-id``, DMI ``product_uuid``
và ``board_serial``. Hash SHA-256 trên các cặp ``key=value`` đã sắp xếp, lấy
10 byte đầu, base32 (không padding) và nhóm 4 ký tự để được mã ngắn dạng
``DSIGHT-7K2M-9QX4-AB12-3C4D``.

Không đọc được host identity (thường chỉ ở dev) thì ``resolve_machine_code``
trả chuỗi rỗng để ``LicenseService`` dùng UUID lưu DB làm fallback — module này
không tự sinh mã, nhờ vậy phần quyết định thuộc về service.
"""
from __future__ import annotations

import base64
import hashlib
import logging
from collections.abc import Mapping
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

MACHINE_CODE_PREFIX = 'DSIGHT'

# Bind mount read-only trong docker-compose. Đặt thành dict để test thay path.
HOST_IDENTITY_PATHS: dict[str, Path] = {
    'machine_id': Path('/host/etc/machine-id'),
    'product_uuid': Path('/host/sys/class/dmi/id/product_uuid'),
    'board_serial': Path('/host/sys/class/dmi/id/board_serial'),
}


def compute_machine_code(sources: Mapping[str, str]) -> str:
    """Tính mã máy deterministic từ ``sources``.

    Chỉ dùng các cặp có key và value khác rỗng, sắp xếp theo chuỗi
    ``key=value`` rồi nối bằng ``|``. Ném ``ValueError`` nếu không còn dữ liệu.
    """
    pairs: list[str] = []
    for key, value in (sources or {}).items():
        clean_key = str(key).strip()
        clean_value = '' if value is None else str(value).strip()
        if clean_key and clean_value:
            pairs.append(f'{clean_key}={clean_value}')

    if not pairs:
        raise ValueError('cannot compute machine code from empty sources')

    digest = hashlib.sha256('|'.join(sorted(pairs)).encode('utf-8')).digest()
    encoded = base64.b32encode(digest[:10]).decode('ascii').rstrip('=').upper()
    groups = [encoded[index:index + 4] for index in range(0, len(encoded), 4)]
    return '-'.join([MACHINE_CODE_PREFIX, *groups])


def read_host_identity() -> dict[str, str]:
    """Đọc các file định danh host; file thiếu/không đọc được bị bỏ qua."""
    identity: dict[str, str] = {}
    for name, path in HOST_IDENTITY_PATHS.items():
        try:
            value = path.read_text(encoding='utf-8').strip()
        except (OSError, UnicodeError):
            continue
        if value:
            identity[name] = value
    return identity


def resolve_machine_code() -> str:
    """Trả mã máy hiệu lực, hoặc ``''`` khi không đọc được host identity.

    ``settings.LICENSE_INSTANCE_ID`` là override chỉ dành cho dev và luôn thắng.
    Fallback UUID (khi trả ``''``) do ``LicenseService`` quản lý và lưu DB.
    """
    override = str(getattr(settings, 'LICENSE_INSTANCE_ID', '') or '').strip()
    if override:
        return override

    sources = read_host_identity()
    if not sources:
        logger.warning(
            'No readable host identity; license machine code falls back to a persisted UUID'
        )
        return ''

    try:
        return compute_machine_code(sources)
    except ValueError:
        logger.warning('Host identity contained no usable values; license machine code unavailable')
        return ''
