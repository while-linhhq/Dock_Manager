from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


def _validate_and_normalize_upper_trim(*, value: object, field_name: str) -> str:
    if value is None:
        raise ValueError(f'{field_name} is required')

    normalized = str(value).strip().upper()
    if not normalized:
        raise ValueError(f'{field_name} must not be empty')

    return normalized


class PatternCreate(BaseModel):
    name: str
    pattern: str
    priority: int = 0
    description: Optional[str] = None
    is_active: bool = True

    @field_validator('pattern', mode='before')
    @classmethod
    def validate_regex(cls, v: object) -> str:
        if v is None:
            raise ValueError('pattern is required')

        normalized = str(v).strip()
        if not normalized:
            raise ValueError('pattern must not be empty')

        try:
            re.compile(normalized)
        except re.error as exc:
            raise ValueError(f'Invalid regex: {exc}') from exc

        return normalized


class PatternUpdate(BaseModel):
    name: Optional[str] = None
    pattern: Optional[str] = None
    priority: Optional[int] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator('pattern', mode='before')
    @classmethod
    def validate_regex(cls, v: Optional[object]) -> Optional[str]:
        if v is None:
            return None

        normalized = str(v).strip()
        if not normalized:
            raise ValueError('pattern must not be empty')

        try:
            re.compile(normalized)
        except re.error as exc:
            raise ValueError(f'Invalid regex: {exc}') from exc

        return normalized


class PatternRead(BaseModel):
    id: int
    name: str
    pattern: str
    priority: int
    description: Optional[str]
    is_active: bool
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class BlacklistCreate(BaseModel):
    value: str
    reason: Optional[str] = None

    @field_validator('value', mode='before')
    @classmethod
    def normalize_value(cls, v: object) -> str:
        return _validate_and_normalize_upper_trim(value=v, field_name='value')


class BlacklistRead(BaseModel):
    id: int
    value: str
    reason: Optional[str]
    created_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class ConvertMapCreate(BaseModel):
    wrong_value: str
    correct_value: str
    reason: Optional[str] = None

    @field_validator('wrong_value', mode='before')
    @classmethod
    def normalize_wrong_value(cls, v: object) -> str:
        return _validate_and_normalize_upper_trim(value=v, field_name='wrong_value')

    @field_validator('correct_value', mode='before')
    @classmethod
    def normalize_correct_value(cls, v: object) -> str:
        return _validate_and_normalize_upper_trim(value=v, field_name='correct_value')

    @model_validator(mode='after')
    def ensure_correct_value_differs(self) -> 'ConvertMapCreate':
        if self.correct_value == self.wrong_value:
            raise ValueError('correct_value must differ from wrong_value')
        return self


class ConvertMapUpdate(BaseModel):
    correct_value: Optional[str] = None
    reason: Optional[str] = None

    @field_validator('correct_value', mode='before')
    @classmethod
    def normalize_correct_value(cls, v: Optional[object]) -> Optional[str]:
        if v is None:
            return None
        return _validate_and_normalize_upper_trim(value=v, field_name='correct_value')


class ConvertMapRead(BaseModel):
    id: int
    wrong_value: str
    correct_value: str
    reason: Optional[str]
    created_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)

