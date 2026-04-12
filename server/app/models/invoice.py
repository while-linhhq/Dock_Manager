from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base


class Invoice(Base):
    __tablename__ = 'invoices'

    id = Column(Integer, primary_key=True, index=True)
    invoice_number = Column(String(50), unique=True, nullable=False)
    order_id = Column(Integer, ForeignKey('orders.id', ondelete='SET NULL'), nullable=True)
    vessel_id = Column(Integer, ForeignKey('vessels.id', ondelete='SET NULL'), nullable=True)
    detection_id = Column(Integer, ForeignKey('detections.id', ondelete='SET NULL'), nullable=True)
    subtotal = Column(Numeric(12, 2), nullable=True)
    tax_amount = Column(Numeric(12, 2), nullable=True)
    total_amount = Column(Numeric(12, 2), nullable=False)
    payment_status = Column(String(20), default='UNPAID')
    due_date = Column(Date, nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    # USER = tạo tay; ORDER_AUTO = sinh khi tạo đơn; AI = pipeline tự động
    creation_source = Column(String(20), nullable=False, default='USER', server_default='USER')
    created_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    order = relationship('Order', back_populates='invoices')
    vessel = relationship('Vessel', back_populates='invoices')
    detection = relationship('Detection', back_populates='invoices')
    creator = relationship('User', foreign_keys=[created_by], back_populates='created_invoices')
    items = relationship('InvoiceItem', back_populates='invoice', cascade='all, delete-orphan')
    payments = relationship('Payment', back_populates='invoice')
