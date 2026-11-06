"""Companies module domain — rules for sign-in credentials (email and password).

One place for both rules so register, login, user creation and password changes agree:

* an email is the same account whatever its case or surrounding spaces
  («Ana@Tienda.pe» and «ana@tienda.pe »);
* every NEW password has at least ``MIN_PASSWORD_LENGTH`` characters. Login never checks
  the length, so users who already have a shorter password can still sign in.
"""
from __future__ import annotations

from app.modules.companies.domain.exceptions import WeakPasswordError

MIN_PASSWORD_LENGTH = 8


def normalize_email(email: str) -> str:
    """Canonical form of an email used to store and look up accounts."""
    return email.strip().lower()


def ensure_new_password(password: str, field: str = "password") -> None:
    """Rejects a new password that is too short (blank-only counts as empty)."""
    length = len(password) if password.strip() else 0
    if length < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(MIN_PASSWORD_LENGTH, length, field)
