from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base


class Order(Base):
    __tablename__ = 'orders'

    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String(50), unique=True, nullable=False, index=True)
    vessel_id = Column(Integer, ForeignKey('vessels.id', ondelete='SET NULL'), nullable=True)
    description = Column(Text, nullable=True)
    total_amount = Column(Numeric(12, 2), nullable=True)
    status = Column(String(20), default='PENDING')  # PENDING | COMPLETED | CANCELLED
    notes = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    updated_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    vessel = relationship('Vessel', back_populates='orders')
    creator = relationship('User', foreign_keys=[created_by], back_populates='created_orders')
    updater = relationship('User', foreign_keys=[updated_by], back_populates='updated_orders')
    invoices = relationship('Invoice', back_populates='order')
