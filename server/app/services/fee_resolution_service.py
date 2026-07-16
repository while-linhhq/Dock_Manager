"""
Nguồn phí DUY NHẤT cho tính hóa đơn / phạt, quyết định theo phân loại tàu.

- spot (tàu lẻ):        phí gắn per-tàu   → fee_config_repo.get_by_vessel(vessel.id)
- monthly (tàu tháng):  phí gắn per-loại  → fee_config_repo.get_by_vessel_type(vessel.vessel_type_id)
- unclassified:         không tính phí    → []

Mọi service tính tiền/phạt phải gọi resolve_billable_fees thay vì gọi thẳng
fee_config_repo.get_by_vessel — để một chỗ đổi là toàn hệ thống nhất quán.
"""

from typing import List, Optional, Union

from sqlalchemy.orm import Session

from app.models.fee import FeeConfig
from app.models.vessel import Vessel


def resolve_billable_fees(
    db: Session,
    vessel_or_id: Union[Vessel, int, None],
    *,
    active_only: bool = True,
) -> List[FeeConfig]:
    """Trả danh sách fee_config áp dụng cho tàu theo phân loại cứng.

    Nhận vessel object (ưu tiên, không query thừa) hoặc vessel_id (tự load).
    """
    # Lazy import: tránh vòng lặp import (repositories/__init__ → invoice → berth_limit → đây).
    from app.repositories.fee_config_repository import fee_config_repo
    from app.repositories.vessel_repository import vessel_repo

    vessel: Optional[Vessel]
    if isinstance(vessel_or_id, int):
        vessel = vessel_repo.get(db, vessel_or_id)
    else:
        vessel = vessel_or_id

    if vessel is None:
        return []

    classification = getattr(vessel, 'classification', 'unclassified') or 'unclassified'

    if classification == 'spot':
        return fee_config_repo.get_by_vessel(db, vessel.id, active_only=active_only)

    if classification == 'monthly':
        if not vessel.vessel_type_id:
            return []
        return fee_config_repo.get_by_vessel_type(
            db, vessel.vessel_type_id, active_only=active_only
        )

    # unclassified (tàu từ nhận diện chưa cấu hình) → không tính phí
    return []
