from fastapi.security import OAuth2PasswordBearer
from app.config import settings

# This scheme will point to the login route, automatically generating Swagger UI components.
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.api_v1_prefix}/auth/login"
)
