from datetime import datetime, timezone
from sqlalchemy import func, or_
from sqlalchemy.orm import Query, Session, joinedload
from app.models.vessel import Vessel
from typing import List, Optional


def _escape_like(value: str) -> str:
    """Escape wildcard của LIKE/ILIKE để `q` chỉ khớp đúng ký tự người dùng gõ."""
    return value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


class VesselRepository:
    def get(self, db: Session, vessel_id: int) -> Optional[Vessel]:
        return (
            db.query(Vessel)
            .options(joinedload(Vessel.vessel_type))
            .filter(Vessel.id == vessel_id)
            .first()
        )

    def get_by_ship_id(self, db: Session, ship_id: str) -> Optional[Vessel]:
        return db.query(Vessel).filter(Vessel.ship_id == ship_id).first()

    def get_by_ship_id_normalized(self, db: Session, ship_id: str) -> Optional[Vessel]:
        """
        Match tàu theo mã đã normalize để chịu được khác biệt chữ hoa/thường
        và khoảng trắng (ví dụ ' sg-8263 ' vẫn khớp 'SG-8263').
        """
        normalized = ship_id.strip().upper()
        if not normalized:
            return None
        return (
            db.query(Vessel)
            .filter(func.upper(func.trim(Vessel.ship_id)) == normalized)
            .first()
        )

    def _filtered_query(
        self,
        db: Session,
        *,
        active_only: bool = False,
        classification: Optional[str] = None,
        q: Optional[str] = None,
    ) -> Query:
        """Query đã áp bộ lọc, dùng chung cho `get_all` và `count_filtered`.

        `q` tìm không phân biệt hoa thường trên `ship_id` **và** tên tàu để dropdown
        chọn tàu không phải tải cả bảng; wildcard trong `q` bị escape nên gõ `%`
        không biến thành "khớp tất cả".
        """
        query = db.query(Vessel)
        if active_only:
            query = query.filter(Vessel.is_active == True)
        if classification:
            query = query.filter(Vessel.classification == classification)
        if q and q.strip():
            pattern = f'%{_escape_like(q.strip())}%'
            query = query.filter(
                or_(
                    Vessel.ship_id.ilike(pattern, escape='\\'),
                    Vessel.name.ilike(pattern, escape='\\'),
                )
            )
        return query

    def get_all(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        active_only: bool = False,
        classification: Optional[str] = None,
        q: Optional[str] = None,
    ) -> List[Vessel]:
        return (
            self._filtered_query(
                db, active_only=active_only, classification=classification, q=q
            )
            .options(joinedload(Vessel.vessel_type))
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_filtered(
        self,
        db: Session,
        *,
        active_only: bool = False,
        classification: Optional[str] = None,
        q: Optional[str] = None,
    ) -> int:
        """Tổng số tàu khớp bộ lọc (trước khi phân trang)."""
        return self._filtered_query(
            db, active_only=active_only, classification=classification, q=q
        ).count()

    def create(self, db: Session, data) -> Vessel:
        payload = data.model_dump() if hasattr(data, 'model_dump') else dict(data)
        db_vessel = Vessel(**payload)
        db.add(db_vessel)
        db.commit()
        db.refresh(db_vessel)
        return db_vessel

    def update(self, db: Session, vessel_id: int, data: dict) -> Optional[Vessel]:
        db_vessel = self.get(db, vessel_id)
        if not db_vessel:
            return None
        for key, value in data.items():
            setattr(db_vessel, key, value)
        db.commit()
        db.refresh(db_vessel)
        return db_vessel

    def update_last_seen(self, db: Session, vessel_id: int) -> Optional[Vessel]:
        db_vessel = self.get(db, vessel_id)
        if db_vessel:
            db_vessel.last_seen = datetime.now(timezone.utc)
            db.commit()
        return db_vessel

    def delete(self, db: Session, vessel_id: int) -> bool:
        db_vessel = self.get(db, vessel_id)
        if not db_vessel:
            return False
        db.delete(db_vessel)
        db.commit()
        return True


vessel_repo = VesselRepository()
