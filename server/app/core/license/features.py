"""Registry feature cấp phép (Keygate) + chuẩn hoá giá trị feature.

Keygate trả feature ``bool`` dưới dạng boolean, còn ``int/string/quota`` dưới
dạng chuỗi (vd ``{"max_cameras": "12"}``). Mọi nơi đọc license phải đi qua
:func:`normalize_features` rồi các helper ``feature_*`` để so sánh đúng kiểu,
và để feature thiếu/hỏng rơi về default AN TOÀN của registry (0 = không có
camera) — tuyệt đối không biến giới hạn thiếu thành "không giới hạn".
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

@dataclass(frozen=True)
class FeatureSpec:
    """Khai báo 1 feature license: kiểu dữ liệu, default an toàn, nhãn hiển thị."""

    type: Literal['bool', 'int', 'string', 'quota']
    default: bool | int | str
    label: str = ''

# Registry feature DUY NHẤT của app. Thêm feature mới = thêm 1 dòng ở đây
# + entitlement/addon tương ứng bên Keygate (không phải sửa kiến trúc chỗ khác).
FEATURES: dict[str, FeatureSpec] = {
    'max_cameras': FeatureSpec('int', 0, 'Số camera tối đa'),
}

def _registry_default(key: str) -> Any:
    """Default của registry cho ``key`` (None nếu key chưa được khai báo)."""
    spec = FEATURES.get(key)
    return spec.default if spec is not None else None

def normalize_features(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Chuẩn hoá dict feature thô từ Keygate theo registry.

    - ``bool``/``flag`` -> bool (True khi gửi boolean True hoặc chuỗi 'true').
    - ``int``/``quota`` -> int nếu ép được, ngược lại default của registry.
    - ``string``        -> str.
    - Key lạ giữ nguyên giá trị, KHÔNG bị ép kiểu và KHÔNG bị chèn default.
    """
    if not isinstance(raw, Mapping):
        return {}
    normalized: dict[str, Any] = {}
    for key, value in raw.items():
        spec = FEATURES.get(key)
        if spec is None:
            normalized[key] = value
        elif spec.type in ('bool', 'flag'):
            normalized[key] = value is True or str(value).lower() == 'true'
        elif spec.type in ('int', 'quota'):
            try:
                normalized[key] = max(int(value), 0)
            except (TypeError, ValueError, OverflowError):
                normalized[key] = spec.default
        else:  # 'string'
            normalized[key] = str(value)
    return normalized

def feature_bool(features: Mapping[str, Any], key: str) -> bool:
    """Đọc feature bool; thiếu/sai kiểu -> default registry, không có spec -> False."""
    value = features.get(key) if isinstance(features, Mapping) else None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.lower()
        if lowered == 'true':
            return True
        if lowered == 'false':
            return False
    default = _registry_default(key)
    return default if isinstance(default, bool) else False

def feature_int(features: Mapping[str, Any], key: str) -> int:
    """Đọc feature int; thiếu/không ép được -> default registry, không có spec -> 0.

    Giá trị âm bị kẹp về 0 (không biến quota âm thành "không giới hạn").
    """
    value = features.get(key) if isinstance(features, Mapping) else None
    # bool là subclass của int nhưng không phải giá trị số hợp lệ cho feature int.
    if not isinstance(value, bool):
        try:
            return max(int(value), 0)
        except (TypeError, ValueError, OverflowError):
            pass
    default = _registry_default(key)
    return default if isinstance(default, int) and not isinstance(default, bool) else 0

def max_cameras(features: Mapping[str, Any]) -> int:
    """Shorthand: giới hạn số camera được cấu hình (0 = không được tạo camera)."""
    return feature_int(features, 'max_cameras')
