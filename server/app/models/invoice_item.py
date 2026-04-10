from sqlalchemy import Column, Integer, String, Numeric, ForeignKey
from sqlalchemy.orm import relationship
from app.db.session import Base


class InvoiceItem(Base):
    __tablename__ = 'invoice_items'

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey('invoices.id', ondelete='CASCADE'), nullable=False)
    fee_config_id = Column(Integer, ForeignKey('fee_configs.id', ondelete='SET NULL'), nullable=True)
    description = Column(String(200), nullable=True)
    quantity = Column(Numeric(10, 2), nullable=True)
    unit_price = Column(Numeric(12, 2), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)

    invoice = relationship('Invoice', back_populates='items')
    fee_config = relationship('FeeConfig', back_populates='invoice_items')
