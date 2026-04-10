from sqlalchemy.orm import Session
from app.models.user import User
from typing import List, Optional


class UserRepository:
    def get(self, db: Session, user_id: int) -> Optional[User]:
        return db.query(User).filter(User.id == user_id).first()

    def get_by_username(self, db: Session, username: str) -> Optional[User]:
        return db.query(User).filter(User.username == username).first()

    def get_by_email(self, db: Session, email: str) -> Optional[User]:
        return db.query(User).filter(User.email == email).first()

    def get_all(self, db: Session, skip: int = 0, limit: int = 100) -> List[User]:
        return db.query(User).offset(skip).limit(limit).all()

    def create(self, db: Session, username: str, hashed_password: str, **kwargs) -> User:
        db_user = User(username=username, hashed_password=hashed_password, **kwargs)
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user

    def update(self, db: Session, user_id: int, **kwargs) -> Optional[User]:
        db_user = self.get(db, user_id)
        if not db_user:
            return None
        for key, value in kwargs.items():
            if value is not None:
                setattr(db_user, key, value)
        db.commit()
        db.refresh(db_user)
        return db_user

    def delete(self, db: Session, user_id: int) -> bool:
        db_user = self.get(db, user_id)
        if not db_user:
            return False
        db_user.is_active = False
        db.commit()
        return True


user_repo = UserRepository()
