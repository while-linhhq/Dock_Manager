from sqlalchemy.orm import Session
from app.models.vessel_type import VesselType
from typing import List, Optional


class VesselTypeRepository:
    def get(self, db: Session, type_id: int) -> Optional[VesselType]:
        return db.query(VesselType).filter(VesselType.id == type_id).first()

    def get_by_name(self, db: Session, type_name: str) -> Optional[VesselType]:
        return db.query(VesselType).filter(VesselType.type_name == type_name).first()

    def get_all(self, db: Session, skip: int = 0, limit: Optional[int] = None) -> List[VesselType]:
        """`limit=None` = không giới hạn (giữ hành vi cũ cho caller khác)."""
        q = db.query(VesselType).offset(skip)
        if limit is not None:
            q = q.limit(limit)
        return q.all()

    def count_all(self, db: Session) -> int:
        """Tổng số loại tàu (trước khi phân trang) — khớp đúng tập `get_all` trả về."""
        return db.query(VesselType).count()


vessel_type_repo = VesselTypeRepository()
