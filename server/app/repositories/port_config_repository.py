from sqlalchemy.orm import Session
from app.models.port import PortConfig
from typing import List, Optional


class PortConfigRepository:
    def create(
        self,
        db: Session,
        key: str,
        value: str,
        description: Optional[str] = None,
        updated_by: Optional[int] = None,
    ) -> PortConfig:
        db_obj = PortConfig(key=key, value=value, description=description, updated_by=updated_by)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get(self, db: Session, config_id: int) -> Optional[PortConfig]:
        return db.query(PortConfig).filter(PortConfig.id == config_id).first()

    def get_by_key(self, db: Session, key: str) -> Optional[PortConfig]:
        return db.query(PortConfig).filter(PortConfig.key == key).first()

    def get_all(self, db: Session, skip: int = 0, limit: Optional[int] = None) -> List[PortConfig]:
        """`limit=None` = không giới hạn.

        Các service (`pipeline_service`, `port_config_runtime`, …) đọc cả bảng để
        dựng map cấu hình, nên mặc định phải giữ nguyên hành vi cũ; endpoint danh
        mục truyền `limit` đã kẹp theo trần catalog.
        """
        q = db.query(PortConfig).offset(skip)
        if limit is not None:
            q = q.limit(limit)
        return q.all()

    def count_all(self, db: Session) -> int:
        """Tổng số config (trước khi phân trang) — khớp đúng tập `get_all` trả về."""
        return db.query(PortConfig).count()

    def upsert(self, db: Session, key: str, value: str, updated_by: Optional[int] = None, description: Optional[str] = None) -> PortConfig:
        db_obj = self.get_by_key(db, key)
        if db_obj:
            db_obj.value = value
            if updated_by is not None:
                db_obj.updated_by = updated_by
            if description is not None:
                db_obj.description = description
        else:
            db_obj = PortConfig(key=key, value=value, updated_by=updated_by, description=description)
            db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete_by_key(self, db: Session, key: str) -> bool:
        db_obj = self.get_by_key(db, key)
        if not db_obj:
            return False
        db.delete(db_obj)
        db.commit()
        return True


port_config_repo = PortConfigRepository()
