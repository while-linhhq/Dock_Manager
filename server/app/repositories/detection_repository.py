from datetime import datetime
from sqlalchemy.orm import Session, joinedload
from app.models.detection import Detection
from typing import List, Optional


class DetectionRepository:
    def get(self, db: Session, detection_id: int) -> Optional[Detection]:
        return (
            db.query(Detection)
            .options(joinedload(Detection.vessel))
            .filter(Detection.id == detection_id)
            .first()
        )

    def get_by_track_id(self, db: Session, track_id: str) -> Optional[Detection]:
        return db.query(Detection).filter(Detection.track_id == track_id).first()

    def get_all(self, db: Session, skip: int = 0, limit: int = 100, vessel_id: Optional[int] = None) -> List[Detection]:
        q = db.query(Detection).options(joinedload(Detection.vessel))
        if vessel_id is not None:
            q = q.filter(Detection.vessel_id == vessel_id)
        return q.order_by(Detection.created_at.desc()).offset(skip).limit(limit).all()

    def create(self, db: Session, data) -> Detection:
        payload = data.model_dump() if hasattr(data, 'model_dump') else dict(data)
        # Ensure vessel_id is present if not provided in data but available via vessel lookup
        db_obj = Detection(**payload)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update_acceptance(self, db: Session, detection_id: int, is_accepted: bool, verified_by: Optional[int] = None, rejection_reason: Optional[str] = None) -> Optional[Detection]:
        db_obj = self.get(db, detection_id)
        if not db_obj:
            return None
        db_obj.is_accepted = is_accepted
        db_obj.verified_at = datetime.utcnow()
        if verified_by:
            db_obj.verified_by = verified_by
        if not is_accepted and rejection_reason:
            db_obj.rejection_reason = rejection_reason
        db.commit()
        return self.get(db, detection_id)

    def delete(self, db: Session, detection_id: int) -> bool:
        db_obj = self.get(db, detection_id)
        if not db_obj:
            return False
        db.delete(db_obj)
        db.commit()
        return True


detection_repo = DetectionRepository()
