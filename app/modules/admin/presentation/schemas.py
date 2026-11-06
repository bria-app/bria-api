"""Admin module — HTTP schemas."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.modules.admin.application.dtos import SystemSettingDTO


class SystemSettingResponse(SystemSettingDTO):
    """Response schema for a system setting."""
    pass


class UpdateSystemSettingRequest(BaseModel):
    """Request schema for updating a system setting."""
    value: dict[str, Any]


# Placeholders for endpoints not fully implemented
class AdminUserResponse(BaseModel):
    message: str
    module: str
    action: str

class AdminCompanyResponse(BaseModel):
    message: str
    module: str
    action: str

class AdminSystemStatusResponse(BaseModel):
    message: str
    module: str
    action: str
