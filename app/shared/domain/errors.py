from typing import Any, Dict, Optional

class DomainError(Exception):
    """Base exception for all domain-related errors."""
    def __init__(self, message: str, code: str = "DOMAIN_ERROR", details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)

class NotFoundError(DomainError):
    def __init__(self, message: str = "No encontramos lo que buscas.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, code="NOT_FOUND", details=details)

class ConflictError(DomainError):
    def __init__(self, message: str = "Ya existe un registro con esos datos.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, code="CONFLICT", details=details)

class ValidationError(DomainError):
    def __init__(self, message: str = "Revisa los datos ingresados.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, code="VALIDATION_ERROR", details=details)

class UnauthorizedError(DomainError):
    def __init__(self, message: str = "Inicia sesión para continuar.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, code="UNAUTHORIZED", details=details)

class ForbiddenError(DomainError):
    def __init__(self, message: str = "No tienes permiso para esta acción.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, code="FORBIDDEN", details=details)
