from sqlalchemy import Column, Integer, String, BigInteger, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base


class DetectionMedia(Base):
    __tablename__ = 'detection_media'

    id = Column(Integer, primary_key=True, index=True)
    detection_id = Column(Integer, ForeignKey('detections.id', ondelete='CASCADE'), nullable=False)
    media_type = Column(String(20), nullable=False)  # image | video | thumbnail
    file_path = Column(String, nullable=False)
    file_size = Column(BigInteger, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    detection = relationship('Detection', back_populates='media')
