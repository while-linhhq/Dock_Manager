from sqlalchemy.orm import Query, Session
from sqlalchemy.orm.attributes import flag_modified
from app.models.camera import Camera
from typing import List, Optional


class CameraRepository:
    def get(self, db: Session, camera_id: int) -> Optional[Camera]:
        return db.query(Camera).filter(Camera.id == camera_id).first()

    def _filtered_query(self, db: Session, *, active_only: bool = False) -> Query:
        """Query đã áp bộ lọc, dùng chung cho `get_all` và `count_all`."""
        q = db.query(Camera)
        if active_only:
            q = q.filter(Camera.is_active == True)
        return q

    def get_active(self, db: Session) -> List[Camera]:
        return self._filtered_query(db, active_only=True).all()

    def get_all(
        self,
        db: Session,
        skip: int = 0,
        limit: Optional[int] = None,
        *,
        active_only: bool = False,
    ) -> List[Camera]:
        """`limit=None` = không giới hạn (giữ hành vi cũ cho caller khác)."""
        q = self._filtered_query(db, active_only=active_only).offset(skip)
        if limit is not None:
            q = q.limit(limit)
        return q.all()

    def count_all(self, db: Session, *, active_only: bool = False) -> int:
        """Tổng số camera khớp bộ lọc (trước khi phân trang)."""
        return self._filtered_query(db, active_only=active_only).count()

    def set_boundary_lines(
        self, db: Session, camera_id: int, payload: Optional[dict]
    ) -> Optional[Camera]:
        obj = self.get(db, camera_id)
        if not obj:
            return None
        obj.boundary_lines = payload
        flag_modified(obj, 'boundary_lines')
        db.commit()
        db.refresh(obj)
        return obj

    def set_detection_settings(
        self, db: Session, camera_id: int, payload: dict
    ) -> Optional[Camera]:
        obj = self.get(db, camera_id)
        if not obj:
            return None
        obj.detection_settings = payload
        flag_modified(obj, 'detection_settings')
        db.commit()
        db.refresh(obj)
        return obj


camera_repo = CameraRepository()
