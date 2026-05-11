from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.camera import CameraRead

FusionMode = Literal['layout']
PipelineMode = Literal['hybrid', 'fused']
MemberRole = Literal['base', 'overlay', 'tile']


class CameraGroupMemberBase(BaseModel):
    camera_id: int
    role: MemberRole = 'tile'
    priority: int = 0
    layout_x: int = 0
    layout_y: int = 0
    layout_w: int | None = None
    layout_h: int | None = None
    layout_rotation: float = 0
    crop_top: int = 0
    crop_bottom: int = 0
    crop_left: int = 0
    crop_right: int = 0
    enabled: bool = True

    @field_validator('layout_w', 'layout_h')
    @classmethod
    def validate_positive_size(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError('layout_w/layout_h must be positive')
        return value

    @field_validator('crop_top', 'crop_bottom', 'crop_left', 'crop_right')
    @classmethod
    def validate_non_negative_crop(cls, value: int) -> int:
        if value < 0:
            raise ValueError('crop values must be non-negative')
        return value


class CameraGroupMemberCreate(CameraGroupMemberBase):
    pass


class CameraGroupMemberUpdate(BaseModel):
    role: MemberRole | None = None
    priority: int | None = None
    layout_x: int | None = None
    layout_y: int | None = None
    layout_w: int | None = None
    layout_h: int | None = None
    layout_rotation: float | None = None
    crop_top: int | None = None
    crop_bottom: int | None = None
    crop_left: int | None = None
    crop_right: int | None = None
    enabled: bool | None = None


class CameraGroupMemberRead(CameraGroupMemberBase):
    id: int
    group_id: int
    created_at: datetime
    updated_at: datetime
    camera: CameraRead | None = None

    model_config = {'from_attributes': True}


class CameraGroupBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    fusion_mode: FusionMode = 'layout'
    pipeline_mode: PipelineMode = 'hybrid'
    canvas_width: int = Field(default=1920, gt=0)
    canvas_height: int = Field(default=1080, gt=0)
    is_active: bool = True


class CameraGroupCreate(CameraGroupBase):
    members: list[CameraGroupMemberCreate] = Field(default_factory=list)


class CameraGroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    fusion_mode: FusionMode | None = None
    pipeline_mode: PipelineMode | None = None
    canvas_width: int | None = Field(default=None, gt=0)
    canvas_height: int | None = Field(default=None, gt=0)
    is_active: bool | None = None
    members: list[CameraGroupMemberCreate] | None = None


class CameraGroupRead(CameraGroupBase):
    id: int
    created_by: int | None = None
    created_at: datetime
    updated_at: datetime
    members: list[CameraGroupMemberRead] = Field(default_factory=list)

    model_config = {'from_attributes': True}


class FusedPreviewRequest(BaseModel):
    fusion_mode: FusionMode = 'layout'
    canvas_width: int = Field(default=1920, gt=0)
    canvas_height: int = Field(default=1080, gt=0)
    members: list[CameraGroupMemberCreate] = Field(min_length=1)
