from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base


class Detection(Base):
    __tablename__ = 'detections'

    id = Column(Integer, primary_key=True, index=True)
    vessel_id = Column(Integer, ForeignKey('vessels.id', ondelete='SET NULL'), nullable=True)
    track_id = Column(String(100), unique=True, index=True)
    start_time = Column(DateTime(timezone=True), nullable=True)
    end_time = Column(DateTime(timezone=True), nullable=True)
    video_path = Column(Text, nullable=True)
    audit_image_path = Column(Text, nullable=True)
    ocr_results = Column(JSONB, nullable=True)
    confidence = Column(Float, nullable=True)
    is_accepted = Column(Boolean, nullable=True)
    verified_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    vessel = relationship('Vessel', back_populates='detections')
    verifier = relationship('User', foreign_keys=[verified_by], back_populates='verified_detections')
    invoices = relationship('Invoice', back_populates='detection')
    media = relationship('DetectionMedia', back_populates='detection', cascade='all, delete-orphan')
