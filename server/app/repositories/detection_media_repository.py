from sqlalchemy.orm import Session
from app.models.detection_media import DetectionMedia
from typing import List, Optional


class DetectionMediaRepository:
    def get(self, db: Session, media_id: int) -> Optional[DetectionMedia]:
        return db.query(DetectionMedia).filter(DetectionMedia.id == media_id).first()

    def get_by_detection(self, db: Session, detection_id: int) -> List[DetectionMedia]:
        return db.query(DetectionMedia).filter(DetectionMedia.detection_id == detection_id).all()

    def create(self, db: Session, data: dict) -> DetectionMedia:
        db_obj = DetectionMedia(**data)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, media_id: int) -> bool:
        db_obj = self.get(db, media_id)
        if not db_obj:
            return False
        db.delete(db_obj)
        db.commit()
        return True


detection_media_repo = DetectionMediaRepository()
