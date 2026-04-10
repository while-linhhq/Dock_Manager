from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base


class Vessel(Base):
    __tablename__ = 'vessels'

    id = Column(Integer, primary_key=True, index=True)
    ship_id = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=True)
    vessel_type_id = Column(Integer, ForeignKey('vessel_types.id', ondelete='SET NULL'), nullable=True)
    owner = Column(String(200), nullable=True)
    registration_number = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    last_seen = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    vessel_type = relationship('VesselType', back_populates='vessels')
    detections = relationship('Detection', back_populates='vessel')
    orders = relationship('Order', back_populates='vessel')
    invoices = relationship('Invoice', back_populates='vessel')
