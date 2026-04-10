from sqlalchemy import Column, Integer, String, Numeric, Boolean, Date, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base


class FeeConfig(Base):
    __tablename__ = 'fee_configs'

    id = Column(Integer, primary_key=True, index=True)
    vessel_type_id = Column(Integer, ForeignKey('vessel_types.id', ondelete='SET NULL'), nullable=True)
    fee_name = Column(String(100), nullable=False)
    base_fee = Column(Numeric(12, 2), nullable=False)
    unit = Column(String(20), nullable=True)
    is_active = Column(Boolean, default=True)
    effective_from = Column(Date, nullable=True)
    effective_to = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    vessel_type = relationship('VesselType', back_populates='fee_configs')
    invoice_items = relationship('InvoiceItem', back_populates='fee_config')
