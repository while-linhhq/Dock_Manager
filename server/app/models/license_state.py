from sqlalchemy import CheckConstraint, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.db.session import Base


class LicenseState(Base):
    """Trạng thái license của bản cài — bảng một dòng duy nhất (id=1)."""

    __tablename__ = 'license_state'
    __table_args__ = (
        CheckConstraint('id = 1', name='chk_license_state_single_row'),
    )

    id = Column(Integer, primary_key=True)
    instance_id = Column(String(64), nullable=False)
    license_key_enc = Column(Text, nullable=True)
    license_id = Column(String(64), nullable=True)
    plan_name = Column(String(120), nullable=True)
    status = Column(String(32), nullable=False, default='unlicensed')
    valid_until = Column(DateTime(timezone=True), nullable=True)
    grace_days = Column(Integer, nullable=False, default=0)
    features = Column(JSONB, nullable=False, default=dict)
    token = Column(Text, nullable=True)
    token_exp = Column(DateTime(timezone=True), nullable=True)
    pubkey = Column(Text, nullable=True)
    last_verified_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    enforcement_mode = Column(String(16), nullable=False, default='warn')
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
