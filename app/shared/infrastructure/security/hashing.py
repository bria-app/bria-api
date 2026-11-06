"""Password hashing using bcrypt directly.

We use the ``bcrypt`` library directly instead of passlib: passlib is effectively
unmaintained and its bcrypt backend is incompatible with bcrypt >= 4.x.

bcrypt only considers the first 72 bytes of the password, so we truncate explicitly
to avoid a ValueError on longer inputs and to keep hashing/verification consistent.
"""
from __future__ import annotations

import bcrypt

_MAX_BCRYPT_BYTES = 72


def _encode(password: str) -> bytes:
    return password.encode("utf-8")[:_MAX_BCRYPT_BYTES]


def hash_password(password: str) -> str:
    """Hash a plain text password using bcrypt; returns the encoded hash string."""
    return bcrypt.hashpw(_encode(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain text password against a bcrypt hash."""
    return bcrypt.checkpw(_encode(plain_password), hashed_password.encode("utf-8"))
