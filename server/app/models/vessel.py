from sqlalchemy import CheckConstraint, Column, Integer, String, Boolean, DateTime, Date, Numeric, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base


class Vessel(Base):
    __tablename__ = 'vessels'
    __table_args__ = (
        CheckConstraint(
            "(classification = 'monthly' AND vessel_type_id IS NOT NULL) OR "
            "(classification IN ('spot', 'unclassified') AND vessel_type_id IS NULL)",
            name='chk_vessels_classification_scope',
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    ship_id = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=True)
    # Phân loại cứng: 'spot' (tàu lẻ, phí per-tàu) | 'monthly' (tàu tháng, phí per-loại)
    # | 'unclassified' (từ nhận diện, chưa cấu hình — không tính phí).
    classification = Column(String(20), nullable=False, server_default='unclassified', index=True)
    vessel_type_id = Column(Integer, ForeignKey('vessel_types.id', ondelete='SET NULL'), nullable=True)
    owner = Column(String(200), nullable=True)
    registration_number = Column(String(100), nullable=True)
    length_m = Column(Numeric(8, 2), nullable=True)  # Chiều dài tàu (mét)
    registry_expiry = Column(Date, nullable=True)  # Ngày hết hạn đăng kiểm
    is_active = Column(Boolean, default=True)
    last_seen = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    vessel_type = relationship('VesselType', back_populates='vessels')
    detections = relationship('Detection', back_populates='vessel')
    orders = relationship('Order', back_populates='vessel')
    invoices = relationship('Invoice', back_populates='vessel')
    fee_configs = relationship('FeeConfig', back_populates='vessel')
