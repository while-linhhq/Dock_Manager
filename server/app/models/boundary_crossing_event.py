from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func

from app.db.session import Base


class BoundaryCrossingEvent(Base):
    __tablename__ = 'boundary_crossing_events'

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(Integer, ForeignKey('cameras.id', ondelete='SET NULL'), nullable=True, index=True)
    track_id = Column(String(100), nullable=False, index=True)
    ship_id = Column(String(50), nullable=True)
    direction = Column(String(10), nullable=False, index=True)
    crossed_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
