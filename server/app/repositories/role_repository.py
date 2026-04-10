from sqlalchemy.orm import Session
from app.models.role import Role
from typing import List, Optional


class RoleRepository:
    def get(self, db: Session, role_id: int) -> Optional[Role]:
        return db.query(Role).filter(Role.id == role_id).first()

    def get_by_name(self, db: Session, role_name: str) -> Optional[Role]:
        return db.query(Role).filter(Role.role_name == role_name).first()

    def get_all(self, db: Session) -> List[Role]:
        return db.query(Role).all()

    def update(self, db: Session, role_id: int, data: dict) -> Optional[Role]:
        db_obj = self.get(db, role_id)
        if not db_obj:
            return None
        for key, value in data.items():
            if value is not None:
                setattr(db_obj, key, value)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, role_id: int) -> bool:
        db_obj = self.get(db, role_id)
        if not db_obj:
            return False
        db.delete(db_obj)
        db.commit()
        return True


role_repo = RoleRepository()
