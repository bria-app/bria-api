from typing import Generic, TypeVar, List, Optional, Any, Dict
from pydantic import BaseModel, Field

T = TypeVar("T")

class PlaceholderResponse(BaseModel):
    message: str
    module: str
    action: str
    status: str = "not_implemented"

class ErrorResponse(BaseModel):
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None

class MessageResponse(BaseModel):
    message: str

class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    size: int
    pages: int

class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=50, ge=1, le=100)
