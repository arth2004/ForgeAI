from typing import Any

from fastapi import status


class ForgeAIException(Exception):
    """Base exception for Forge AI domain errors."""
    def __init__(self, message: str, status_code: int = status.HTTP_400_BAD_REQUEST, details: dict[str, Any] | None = None):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class NotFoundException(ForgeAIException):
    def __init__(self, resource: str, identifier: Any):
        super().__init__(
            message=f"{resource} with identifier '{identifier}' was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class UnauthorizedException(ForgeAIException):
    def __init__(self, message: str = "Invalid credentials or unauthorized access."):
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class ForbiddenException(ForgeAIException):
    def __init__(self, message: str = "Access forbidden for current user or tenant."):
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
        )


class ConflictException(ForgeAIException):
    def __init__(self, message: str = "Resource already exists or constraint violated."):
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
        )
