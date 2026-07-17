from sqlalchemy import CheckConstraint, Column, Integer, String, Numeric, Boolean, Date, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base


class FeeConfig(Base):
    __tablename__ = 'fee_configs'
    __table_args__ = (
        CheckConstraint(
            'is_active = FALSE OR '
            '(vessel_id IS NOT NULL AND vessel_type_id IS NULL) OR '
            '(vessel_id IS NULL AND vessel_type_id IS NOT NULL)',
            name='chk_fee_configs_exactly_one_scope',
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    # DEPRECATED: fee giờ gắn trực tiếp vessel_id. Giữ cột để rollback an toàn, không dùng để resolve.
    vessel_type_id = Column(Integer, ForeignKey('vessel_types.id', ondelete='SET NULL'), nullable=True)
    vessel_id = Column(Integer, ForeignKey('vessels.id', ondelete='CASCADE'), nullable=True, index=True)
    fee_name = Column(String(100), nullable=False)
    base_fee = Column(Numeric(12, 2), nullable=False)
    unit = Column(String(20), nullable=True)
    is_active = Column(Boolean, default=True)
    effective_from = Column(Date, nullable=True)
    effective_to = Column(Date, nullable=True)
    berth_limit_count = Column(Integer, nullable=True)
    berth_limit_unit = Column(String(10), nullable=True)  # day | month
    over_limit_penalty_amount = Column(Numeric(12, 2), nullable=True)
    outside_hours_penalty_amount = Column(Numeric(12, 2), nullable=True)
    # Phạt neo ngoài giờ TÍNH THEO GIỜ (chỉ áp cho tàu tháng): đơn giá ₫/giờ,
    # nhân với số giờ neo thực tế NẰM NGOÀI khung cho phép (không làm tròn).
    outside_hours_penalty_per_hour = Column(Numeric(12, 2), nullable=True)
    # Giới hạn thời gian cho MỘT lần neo đậu (phút) + phí phạt khi vượt.
    max_berth_duration_minutes = Column(Integer, nullable=True)
    over_duration_penalty_amount = Column(Numeric(12, 2), nullable=True)
    operating_hours = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    vessel_type = relationship('VesselType', back_populates='fee_configs')
    vessel = relationship('Vessel', back_populates='fee_configs')
    invoice_items = relationship('InvoiceItem', back_populates='fee_config')
