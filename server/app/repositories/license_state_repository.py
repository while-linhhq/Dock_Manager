from __future__ import annotations

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.license_state import LicenseState


class LicenseStateRepository:
    """Truy cập bảng một dòng ``license_state`` (id=1).

    Repository chỉ ``flush``, không ``commit`` — caller quyết định ranh giới
    transaction (giống các repository khác trong project).
    """

    def get(self, db: Session) -> LicenseState | None:
        return db.get(LicenseState, 1)

    def ensure(self, db: Session, instance_id: str) -> LicenseState:
        """Trả row id=1; tạo mới nếu chưa có.

        ``instance_id`` của row đã tồn tại **không bao giờ bị ghi đè**: mã máy
        khác mã đã lưu là bất thường (copy bộ cài/đổi phần cứng) và do
        ``LicenseService`` quyết định, không phải repository.
        """
        row = self.get(db)
        if row is not None:
            return row

        row = LicenseState(id=1, instance_id=instance_id)
        db.add(row)
        db.flush()
        return row

    def update(self, db: Session, **fields) -> LicenseState:
        """Cập nhật các cột được truyền vào row id=1 rồi flush."""
        row = self.get(db)
        if row is None:
            raise RuntimeError('license_state row does not exist; call ensure() first')

        columns = LicenseState.__table__.columns
        for name, value in fields.items():
            if name not in columns:
                raise ValueError(f'unknown license_state field: {name}')
            setattr(row, name, value)
            if name == 'features':
                # JSONB là mutable type: đánh dấu dirty phòng khi caller truyền
                # đúng object dict đã bị sửa tại chỗ.
                flag_modified(row, 'features')

        db.flush()
        return row


license_state_repo = LicenseStateRepository()
