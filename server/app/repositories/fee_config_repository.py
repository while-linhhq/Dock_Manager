from sqlalchemy.orm import Session
from app.models.fee import FeeConfig
from typing import List, Optional


class FeeConfigRepository:
    def get(self, db: Session, fee_id: int) -> Optional[FeeConfig]:
        return db.query(FeeConfig).filter(FeeConfig.id == fee_id).first()

    def get_all(self, db: Session, skip: int = 0, limit: int = 100, active_only: bool = False) -> List[FeeConfig]:
        q = db.query(FeeConfig)
        if active_only:
            q = q.filter(FeeConfig.is_active == True)
        return q.offset(skip).limit(limit).all()

    def get_by_vessel_type(self, db: Session, vessel_type_id: int) -> List[FeeConfig]:
        return db.query(FeeConfig).filter(
            FeeConfig.vessel_type_id == vessel_type_id,
            FeeConfig.is_active == True,
        ).all()

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
            if value is not None:
                setattr(db_obj, key, value)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, fee_id: int) -> bool:
        db_obj = self.get(db, fee_id)
        if not db_obj:
            return False
        db_obj.is_active = False
        db.commit()
        return True


fee_config_repo = FeeConfigRepository()
