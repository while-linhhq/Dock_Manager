from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.camera import CameraRead

FusionMode = Literal['layout', 'homography', 'panorama']
MemberRole = Literal['base', 'overlay', 'tile']
PointPair = dict[str, list[float]]
Homography = list[list[float]]


class CameraGroupMemberBase(BaseModel):
    camera_id: int
    role: MemberRole = 'tile'
    priority: int = 0
    layout_x: int = 0
    layout_y: int = 0
    layout_w: int | None = None
    layout_h: int | None = None
    layout_rotation: float = 0
    homography: Homography | None = None
    calibration_points: list[PointPair] | None = None
    enabled: bool = True

    @field_validator('layout_w', 'layout_h')
    @classmethod
    def validate_positive_size(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError('layout_w/layout_h must be positive')
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
    homography: Homography | None = None
    calibration_points: list[PointPair] | None = None
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
    canvas_width: int = Field(default=1920, gt=0)
    canvas_height: int = Field(default=1080, gt=0)
    stitch_metadata: dict | None = None
    is_active: bool = True


class CameraGroupCreate(CameraGroupBase):
    members: list[CameraGroupMemberCreate] = Field(default_factory=list)


class CameraGroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    fusion_mode: FusionMode | None = None
    canvas_width: int | None = Field(default=None, gt=0)
    canvas_height: int | None = Field(default=None, gt=0)
    stitch_metadata: dict | None = None
    is_active: bool | None = None
    members: list[CameraGroupMemberCreate] | None = None


class CameraGroupRead(CameraGroupBase):
    id: int
    created_by: int | None = None
    created_at: datetime
    updated_at: datetime
    members: list[CameraGroupMemberRead] = Field(default_factory=list)

    model_config = {'from_attributes': True}


class CalibrationPointPair(BaseModel):
    src: tuple[float, float]
    dst: tuple[float, float]
    label: str | None = None


class CalibrationComputeRequest(BaseModel):
    points: list[CalibrationPointPair] = Field(min_length=4)


class CalibrationComputeResponse(BaseModel):
    homography: Homography
    inliers: int


class AutoCalibrateRequest(BaseModel):
    reference_camera_id: int | None = None


class PairMatchStat(BaseModel):
    source_camera_id: int
    target_camera_id: int
    matches: int
    inliers: int
    confidence: float


class AutoCalibrateResponse(BaseModel):
    reference_camera_id: int
    canvas_width: int
    canvas_height: int
    pair_stats: list[PairMatchStat]
    unmatched_camera_ids: list[int] = Field(default_factory=list)


class FusedPreviewRequest(BaseModel):
    fusion_mode: FusionMode = 'layout'
    canvas_width: int = Field(default=1920, gt=0)
    canvas_height: int = Field(default=1080, gt=0)
    members: list[CameraGroupMemberCreate] = Field(min_length=1)
