from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, Numeric, String
from sqlalchemy.sql import func

from app.db.session import Base


class BulkPaymentSession(Base):
    __tablename__ = 'bulk_payment_sessions'

    id = Column(Integer, primary_key=True, index=True)
    reference_code = Column(String(64), unique=True, nullable=False, index=True)
    invoice_ids = Column(JSON, nullable=False)
    expected_total = Column(Numeric(12, 2), nullable=False)
    status = Column(String(20), nullable=False, default='pending', server_default='pending')
    sepay_txn_id = Column(Integer, nullable=True)
    created_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
