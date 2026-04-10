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

    def get_all(self, db: Session) -> List[PortConfig]:
        return db.query(PortConfig).all()

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
