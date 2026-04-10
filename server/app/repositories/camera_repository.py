from sqlalchemy.orm import Session
from app.models.camera import Camera
from typing import List, Optional


class CameraRepository:
    def get(self, db: Session, camera_id: int) -> Optional[Camera]:
        return db.query(Camera).filter(Camera.id == camera_id).first()

    def get_active(self, db: Session) -> List[Camera]:
        return db.query(Camera).filter(Camera.is_active == True).all()

    def get_all(self, db: Session) -> List[Camera]:
        return db.query(Camera).all()


camera_repo = CameraRepository()
