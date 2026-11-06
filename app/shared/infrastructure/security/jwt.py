from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, cast
from jose import jwt, JWTError
from app.config import settings
from app.shared.domain.errors import UnauthorizedError

def create_access_token(subject: str | Any, extra_claims: Optional[Dict[str, Any]] = None) -> str:
    """Creates a short-lived access token for the given subject."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode = {"exp": expire, "sub": str(subject)}
    if extra_claims:
        to_encode.update(extra_claims)
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return cast(str, encoded_jwt)

def create_refresh_token(subject: str | Any) -> str:
    """Creates a long-lived refresh token for the given subject."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.refresh_token_expire_minutes)
    to_encode = {"exp": expire, "sub": str(subject), "type": "refresh"}
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return cast(str, encoded_jwt)

def decode_token(token: str) -> Dict[str, Any]:
    """Decodes a JWT and returns its claims. Raises UnauthorizedError if invalid or expired."""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return cast(Dict[str, Any], payload)
    except JWTError as e:
        raise UnauthorizedError(message="Tu sesión expiró. Vuelve a iniciar sesión.") from e
