from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=True)
    email = Column(String(100), unique=True, nullable=True)
    full_name = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=True)
    role_id = Column(Integer, ForeignKey('roles.id', ondelete='SET NULL'), nullable=True)
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    role = relationship('Role', back_populates='users')
    verified_detections = relationship('Detection', foreign_keys='Detection.verified_by', back_populates='verifier')
    created_orders = relationship('Order', foreign_keys='Order.created_by', back_populates='creator')
    updated_orders = relationship('Order', foreign_keys='Order.updated_by', back_populates='updater')
    created_invoices = relationship('Invoice', foreign_keys='Invoice.created_by', back_populates='creator')
    created_payments = relationship('Payment', foreign_keys='Payment.created_by', back_populates='creator')
    audit_logs = relationship('AuditLog', back_populates='user')
    export_logs = relationship('ExportLog', back_populates='user')
