from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.shared.infrastructure.database.portable import UTCDateTime

class Base(DeclarativeBase):
    """Base class for all SQLAlchemy declarative models."""
    pass

class TimestampMixin:
    """Mixin to add created_at and updated_at timestamps."""
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

class UUIDMixin:
    """Mixin to add a UUID primary key."""
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

class CompanyOwnedMixin:
    """Mixin for models that belong to a specific company, used for multi-tenancy."""
    company_id: Mapped[UUID] = mapped_column(index=True, nullable=False)

# Optional helper class combining the most common base elements.
# Named BaseEntity (not BaseModel) to avoid confusion with Pydantic's BaseModel.
class BaseEntity(Base, UUIDMixin, TimestampMixin):
    __abstract__ = True
