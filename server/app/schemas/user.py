from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional, Any


class UserRoleBrief(BaseModel):
    id: int
    role_name: str
    description: Optional[str] = None
    permissions: Optional[dict[str, Any]] = None

    model_config = {'from_attributes': True}


class UserBase(BaseModel):
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    role_id: Optional[int] = None
    is_active: bool = True


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    email: Optional[str] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    role_id: Optional[int] = None
    is_active: Optional[bool] = None


class UserRead(UserBase):
    id: int
    last_login: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    role: Optional[UserRoleBrief] = None

    model_config = {'from_attributes': True}


class UserSelfUpdate(BaseModel):
    email: Optional[str] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    password: Optional[str] = None
