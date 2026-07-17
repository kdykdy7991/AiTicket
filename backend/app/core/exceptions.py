"""Custom exception hierarchy and global handler."""

import logging

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("skdy.api")


class AppException(Exception):
    """Base application exception."""
    def __init__(self, code: str, message: str, status_code: int = 400, details=None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


class NotFoundError(AppException):
    def __init__(self, resource: str, resource_id=None):
        super().__init__(
            code=f"{resource.upper()}_NOT_FOUND",
            message=f"{resource}不存在" + (f" (id={resource_id})" if resource_id else ""),
            status_code=404,
        )


class ForbiddenError(AppException):
    def __init__(self, message: str = "无权限访问"):
        super().__init__(code="FORBIDDEN", message=message, status_code=403)


class ConflictError(AppException):
    def __init__(self, message: str):
        super().__init__(code="CONFLICT", message=message, status_code=409)


class StateTransitionError(AppException):
    def __init__(self, from_state: str, to_state: str):
        super().__init__(
            code="INVALID_STATE_TRANSITION",
            message=f"不允许从「{from_state}」变更为「{to_state}」",
            status_code=400,
        )


async def app_exception_handler(request: Request, exc: AppException):
    logger.warning(
        "app exception: %s - %s",
        exc.code,
        exc.message,
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": exc.status_code,
        },
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
    )
