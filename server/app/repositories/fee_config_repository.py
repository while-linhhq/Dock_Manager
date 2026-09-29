from sqlalchemy.orm import Query, Session, joinedload
from app.models.fee import FeeConfig
from typing import List, Optional


class FeeConfigRepository:
    def get(self, db: Session, fee_id: int) -> Optional[FeeConfig]:
        return (
            db.query(FeeConfig)
            .options(joinedload(FeeConfig.vessel_type), joinedload(FeeConfig.vessel))
            .filter(FeeConfig.id == fee_id)
            .first()
        )

    def _filtered_query(
        self,
        db: Session,
        *,
        active_only: bool = False,
        vessel_id: Optional[int] = None,
        vessel_type_id: Optional[int] = None,
    ) -> Query:
        """Query đã áp bộ lọc, dùng chung cho `get_all`/`get_by_*` và `count_filtered`.

        Phạm vi phí là "hoặc tàu hoặc loại tàu", nên nhánh lọc nào cũng kèm điều
        kiện `IS NULL` ở vế còn lại — giống hệt `get_by_vessel`/`get_by_vessel_type`.
        """
        q = db.query(FeeConfig)
        if vessel_id is not None:
            q = q.filter(FeeConfig.vessel_id == vessel_id, FeeConfig.vessel_type_id.is_(None))
        elif vessel_type_id is not None:
            q = q.filter(FeeConfig.vessel_type_id == vessel_type_id, FeeConfig.vessel_id.is_(None))
        if active_only:
            q = q.filter(FeeConfig.is_active == True)
        return q

    def get_all(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        active_only: bool = False,
        vessel_id: Optional[int] = None,
        vessel_type_id: Optional[int] = None,
    ) -> List[FeeConfig]:
        return (
            self._filtered_query(
                db,
                active_only=active_only,
                vessel_id=vessel_id,
                vessel_type_id=vessel_type_id,
            )
            .options(joinedload(FeeConfig.vessel_type), joinedload(FeeConfig.vessel))
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_filtered(
        self,
        db: Session,
        *,
        active_only: bool = False,
        vessel_id: Optional[int] = None,
        vessel_type_id: Optional[int] = None,
    ) -> int:
        """Tổng số fee config khớp bộ lọc (trước khi phân trang)."""
        return self._filtered_query(
            db,
            active_only=active_only,
            vessel_id=vessel_id,
            vessel_type_id=vessel_type_id,
        ).count()

    def get_by_ids(self, db: Session, fee_ids: List[int]) -> List[FeeConfig]:
        if not fee_ids:
            return []
        rows = (
            db.query(FeeConfig)
            .options(joinedload(FeeConfig.vessel_type))
            .filter(FeeConfig.id.in_(fee_ids))
            .all()
        )
        order = {fid: idx for idx, fid in enumerate(fee_ids)}
        rows.sort(key=lambda row: order.get(row.id, 10**9))
        return rows

    def get_by_vessel_type(
        self, db: Session, vessel_type_id: int, *, active_only: bool = True
    ) -> List[FeeConfig]:
        """Fee config gắn theo loại tàu — đường chính cho tàu tháng (monthly)."""
        return (
            self._filtered_query(
                db, vessel_type_id=vessel_type_id, active_only=active_only
            )
            .options(joinedload(FeeConfig.vessel_type), joinedload(FeeConfig.vessel))
            .all()
        )

    def get_by_vessel(self, db: Session, vessel_id: int, *, active_only: bool = True) -> List[FeeConfig]:
        """Fee config gắn trực tiếp mã tàu (thay cho resolve theo loại tàu)."""
        return (
            self._filtered_query(db, vessel_id=vessel_id, active_only=active_only)
            .options(joinedload(FeeConfig.vessel_type), joinedload(FeeConfig.vessel))
            .all()
        )

    def create(self, db: Session, data: dict) -> FeeConfig:
        db_obj = FeeConfig(**data)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(self, db: Session, fee_id: int, data: dict) -> Optional[FeeConfig]:
        db_obj = self.get(db, fee_id)
        if not db_obj:
            return None
        for key, value in data.items():
            setattr(db_obj, key, value)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, fee_id: int) -> bool:
        db_obj = self.get(db, fee_id)
        if not db_obj:
            return False
        db.delete(db_obj)
        db.commit()
        return True


fee_config_repo = FeeConfigRepository()
