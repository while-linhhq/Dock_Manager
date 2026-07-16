from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


def _validate_non_empty_trim(*, value: object, field_name: str) -> str:
    if value is None:
        raise ValueError(f'{field_name} is required')

    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f'{field_name} must not be empty')

    return normalized


def _validate_and_normalize_upper_trim(*, value: object, field_name: str) -> str:
    return _validate_non_empty_trim(value=value, field_name=field_name).upper()


class PatternCreate(BaseModel):
    name: str
    pattern: str
    priority: int = 0
    description: Optional[str] = None
    is_active: bool = True

    @field_validator('name', mode='before')
    @classmethod
    def validate_name(cls, v: object) -> str:
        return _validate_non_empty_trim(value=v, field_name='name')

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

    @field_validator('name', mode='before')
    @classmethod
    def validate_name(cls, v: Optional[object]) -> Optional[str]:
        if v is None:
            return None
        return _validate_non_empty_trim(value=v, field_name='name')

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


def _validate_prefix(*, value: object, field_name: str) -> str:
    """Prefix must be 1-10 letters only (A-Z), normalized upper-case."""
    normalized = _validate_and_normalize_upper_trim(value=value, field_name=field_name)
    if not re.fullmatch(r'[A-Z]{1,10}', normalized):
        raise ValueError(f'{field_name} must be 1-10 letters (A-Z) only')
    return normalized


class PrefixConvertCreate(BaseModel):
    from_prefix: str
    to_prefix: str
    reason: Optional[str] = None

    @field_validator('from_prefix', mode='before')
    @classmethod
    def normalize_from_prefix(cls, v: object) -> str:
        return _validate_prefix(value=v, field_name='from_prefix')

    @field_validator('to_prefix', mode='before')
    @classmethod
    def normalize_to_prefix(cls, v: object) -> str:
        return _validate_prefix(value=v, field_name='to_prefix')

    @model_validator(mode='after')
    def ensure_to_prefix_differs(self) -> 'PrefixConvertCreate':
        if self.from_prefix == self.to_prefix:
            raise ValueError('to_prefix must differ from from_prefix')
        return self


class PrefixConvertUpdate(BaseModel):
    to_prefix: Optional[str] = None
    reason: Optional[str] = None

    @field_validator('to_prefix', mode='before')
    @classmethod
    def normalize_to_prefix(cls, v: Optional[object]) -> Optional[str]:
        if v is None:
            return None
        return _validate_prefix(value=v, field_name='to_prefix')


class PrefixConvertRead(BaseModel):
    id: int
    from_prefix: str
    to_prefix: str
    reason: Optional[str]
    created_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)

