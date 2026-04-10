from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base


class VesselType(Base):
    __tablename__ = 'vessel_types'

    id = Column(Integer, primary_key=True, index=True)
    type_name = Column(String(50), unique=True, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    vessels = relationship('Vessel', back_populates='vessel_type')
    fee_configs = relationship('FeeConfig', back_populates='vessel_type')
