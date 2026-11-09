"""Pydantic schemas cho license API (Task 8)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

LicenseEnforcementMode = Literal['off', 'warn', 'enforce']


class LicenseStatusRead(BaseModel):
    """Ảnh chụp trạng thái license cho FE (không chứa license key thật)."""

    status: str
    plan_name: str | None = None
    valid_until: datetime | None = None
    days_left: int | None = None
    grace_days: int
    features: dict[str, Any]
    enforcement_mode: LicenseEnforcementMode
    instance_id: str
    machine_code: str
    license_key_hint: str | None = None
    last_verified_at: datetime | None = None
    last_error: str | None = None


class LicenseActivateRequest(BaseModel):
    license_key: str
    label: str = ''


class LicenseEnforcementUpdate(BaseModel):
    mode: LicenseEnforcementMode
