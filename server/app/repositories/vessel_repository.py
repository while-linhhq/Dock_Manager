from datetime import datetime
from sqlalchemy.orm import Session
from app.models.vessel import Vessel
from typing import List, Optional


class VesselRepository:
    def get(self, db: Session, vessel_id: int) -> Optional[Vessel]:
        return db.query(Vessel).filter(Vessel.id == vessel_id).first()

    def get_by_ship_id(self, db: Session, ship_id: str) -> Optional[Vessel]:
        return db.query(Vessel).filter(Vessel.ship_id == ship_id).first()

    def get_all(self, db: Session, skip: int = 0, limit: int = 100, active_only: bool = False) -> List[Vessel]:
        q = db.query(Vessel)
        if active_only:
            q = q.filter(Vessel.is_active == True)
        return q.offset(skip).limit(limit).all()

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
            if value is not None:
                setattr(db_vessel, key, value)
        db.commit()
        db.refresh(db_vessel)
        return db_vessel

    def update_last_seen(self, db: Session, vessel_id: int) -> Optional[Vessel]:
        db_vessel = self.get(db, vessel_id)
        if db_vessel:
            db_vessel.last_seen = datetime.utcnow()
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
