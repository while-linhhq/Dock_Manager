from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from app.db.session import Base


class ZaloNotification(Base):
    __tablename__ = 'zalo_notifications'
    __table_args__ = (
        UniqueConstraint(
            'detection_id',
            'kind',
            name='uq_zalo_notifications_detection_kind',
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    detection_id = Column(
        Integer,
        ForeignKey('detections.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    chat_id = Column(String(100), nullable=True)
    status = Column(String(20), nullable=False, server_default='sent')
    # 'unknown' = tàu chưa xác định (SKIP = xóa detection);
    # 'embedding_confirm' = nhận diện bằng embedding, chờ xác nhận (SKIP = giữ nguyên);
    # registry_expired/outside_hours/over_duration = cảnh báo nghiệp vụ, không tương tác.
    kind = Column(String(24), nullable=False, server_default='unknown')
    header_message_id = Column(String(64), nullable=True)
    photo_message_id = Column(String(64), nullable=True)
    video_message_id = Column(String(64), nullable=True)
    resolved_ship_id = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)
