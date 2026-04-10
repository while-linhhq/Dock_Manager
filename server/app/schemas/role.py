from pydantic import BaseModel
from typing import Optional, Any


class RoleBase(BaseModel):
    role_name: str
    description: Optional[str] = None
    permissions: Optional[dict[str, Any]] = None


class RoleCreate(RoleBase):
    pass


class RoleRead(RoleBase):
    id: int

    model_config = {'from_attributes': True}


class RoleUpdate(BaseModel):
    role_name: Optional[str] = None
    description: Optional[str] = None
    permissions: Optional[dict[str, Any]] = None
