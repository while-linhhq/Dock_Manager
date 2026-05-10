from __future__ import annotations

from typing import Sequence

from sqlalchemy.orm import Session, joinedload

from app.models.camera_group import CameraGroup, CameraGroupMember
from app.schemas.camera_group import CameraGroupCreate, CameraGroupUpdate


class CameraGroupRepository:
    def get(self, db: Session, group_id: int) -> CameraGroup | None:
        return (
            db.query(CameraGroup)
            .options(joinedload(CameraGroup.members).joinedload(CameraGroupMember.camera))
            .filter(CameraGroup.id == group_id)
            .first()
        )

    def get_all(self, db: Session, active_only: bool = False) -> list[CameraGroup]:
        query = db.query(CameraGroup).options(
            joinedload(CameraGroup.members).joinedload(CameraGroupMember.camera)
        )
        if active_only:
            query = query.filter(CameraGroup.is_active.is_(True))
        return query.order_by(CameraGroup.id.desc()).all()

    def create(
        self,
        db: Session,
        data: CameraGroupCreate,
        created_by: int | None = None,
    ) -> CameraGroup:
        payload = data.model_dump(exclude={'members'})
        group = CameraGroup(**payload, created_by=created_by)
        db.add(group)
        db.flush()
        self._replace_members(db, group.id, data.members)
        db.commit()
        return self.get(db, group.id) or group

    def update(self, db: Session, group: CameraGroup, data: CameraGroupUpdate) -> CameraGroup:
        payload = data.model_dump(exclude_unset=True, exclude={'members'})
        for key, value in payload.items():
            setattr(group, key, value)
        if data.members is not None:
            self._replace_members(db, group.id, data.members)
        db.commit()
        return self.get(db, group.id) or group

    def delete(self, db: Session, group: CameraGroup) -> None:
        db.delete(group)
        db.commit()

    def set_members(
        self,
        db: Session,
        group_id: int,
        members: Sequence,
    ) -> CameraGroup | None:
        self._replace_members(db, group_id, members)
        db.commit()
        return self.get(db, group_id)

    def _replace_members(self, db: Session, group_id: int, members: Sequence) -> None:
        db.query(CameraGroupMember).filter(CameraGroupMember.group_id == group_id).delete()
        for member in members:
            db.add(CameraGroupMember(group_id=group_id, **member.model_dump()))


camera_group_repo = CameraGroupRepository()
