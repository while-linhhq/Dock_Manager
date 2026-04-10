from sqlalchemy.orm import Session
from app.models.vessel_type import VesselType
from typing import List, Optional


class VesselTypeRepository:
    def get(self, db: Session, type_id: int) -> Optional[VesselType]:
        return db.query(VesselType).filter(VesselType.id == type_id).first()

    def get_by_name(self, db: Session, type_name: str) -> Optional[VesselType]:
        return db.query(VesselType).filter(VesselType.type_name == type_name).first()

    def get_all(self, db: Session) -> List[VesselType]:
        return db.query(VesselType).all()


vessel_type_repo = VesselTypeRepository()
