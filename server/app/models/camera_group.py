from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base


class CameraGroup(Base):
    __tablename__ = 'camera_groups'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    fusion_mode = Column(String(20), nullable=False, default='layout')
    canvas_width = Column(Integer, nullable=False, default=1920)
    canvas_height = Column(Integer, nullable=False, default=1080)
    stitch_metadata = Column(JSONB, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    members = relationship(
        'CameraGroupMember',
        back_populates='group',
        cascade='all, delete-orphan',
        order_by='CameraGroupMember.priority',
    )


class CameraGroupMember(Base):
    __tablename__ = 'camera_group_members'
    __table_args__ = (UniqueConstraint('group_id', 'camera_id', name='uq_camera_group_member'),)

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey('camera_groups.id', ondelete='CASCADE'), nullable=False)
    camera_id = Column(Integer, ForeignKey('cameras.id', ondelete='CASCADE'), nullable=False)
    role = Column(String(20), nullable=False, default='tile')
    priority = Column(Integer, nullable=False, default=0)
    layout_x = Column(Integer, nullable=False, default=0)
    layout_y = Column(Integer, nullable=False, default=0)
    layout_w = Column(Integer, nullable=True)
    layout_h = Column(Integer, nullable=True)
    layout_rotation = Column(Float, nullable=False, default=0)
    homography = Column(JSONB, nullable=True)
    calibration_points = Column(JSONB, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    group = relationship('CameraGroup', back_populates='members')
    camera = relationship('Camera')
