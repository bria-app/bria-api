"""Companies module domain — enums."""
from __future__ import annotations

from enum import StrEnum


class CompanyPlan(StrEnum):
    FREE = "free"
    PREMIUM = "premium"


class CompanyStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class UserRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"
    SELLER = "seller"  # cashier: runs the POS, nothing else


class UserStatus(StrEnum):
    ACTIVE = "active"
    INVITED = "invited"
    DISABLED = "disabled"
