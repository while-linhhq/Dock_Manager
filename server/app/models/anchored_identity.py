from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, LargeBinary, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.db.session import Base


class AnchoredIdentity(Base):
    __tablename__ = 'anchored_identities'

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey('camera_groups.id', ondelete='CASCADE'), nullable=True)
    global_id = Column(String(80), unique=True, nullable=False, index=True)
    ship_id = Column(String(80), nullable=True, index=True)
    track_id = Column(String(100), nullable=True)
    cam_a_id = Column(Integer, ForeignKey('cameras.id', ondelete='SET NULL'), nullable=True)
    cam_b_id = Column(Integer, ForeignKey('cameras.id', ondelete='SET NULL'), nullable=True)
    bbox_a = Column(JSONB, nullable=False)
    bbox_b = Column(JSONB, nullable=True)
    embedding = Column(LargeBinary, nullable=True)
    embedding_shape = Column(JSONB, nullable=True)
    ocr_history = Column(JSONB, nullable=True)
    first_seen_at = Column(DateTime(timezone=True), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), nullable=False)
    anchored_at = Column(DateTime(timezone=True), nullable=False)
    last_track = Column(JSONB, nullable=True)
    confidence = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


Index('ix_anchored_identities_group_id', AnchoredIdentity.group_id)
