"""Application exceptions and RFC/contract-compliant error response structures."""
import uuid
from typing import Any, Dict, Optional
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class FloodLensAPIException(Exception):
    """Base exception for application errors following contract format."""

    def __init__(self, code: str, message: str, status_code: int = status.HTTP_400_BAD_REQUEST, details: Optional[Dict[str, Any]] = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class NotFoundError(FloodLensAPIException):
    def __init__(self, message: str = "Resource not found", code: str = "NOT_FOUND"):
        super().__init__(code=code, message=message, status_code=status.HTTP_404_NOT_FOUND)


class UnauthorizedError(FloodLensAPIException):
    def __init__(self, message: str = "Authentication required", code: str = "UNAUTHORIZED"):
        super().__init__(code=code, message=message, status_code=status.HTTP_401_UNAUTHORIZED)


class ForbiddenError(FloodLensAPIException):
    def __init__(self, message: str = "Insufficient permissions", code: str = "FORBIDDEN"):
        super().__init__(code=code, message=message, status_code=status.HTTP_403_FORBIDDEN)


class DataUnavailableError(FloodLensAPIException):
    def __init__(self, message: str = "Requested observation or data source unavailable", code: str = "DATA_UNAVAILABLE"):
        super().__init__(code=code, message=message, status_code=status.HTTP_404_NOT_FOUND)


class ConflictError(FloodLensAPIException):
    def __init__(self, message: str = "Resource conflict", code: str = "CONFLICT"):
        super().__init__(code=code, message=message, status_code=status.HTTP_409_CONFLICT)


def get_request_id(request: Request) -> str:
    """Retrieve or generate correlation request ID."""
    return getattr(request.state, "request_id", None) or f"req_{uuid.uuid4().hex[:8]}"


def make_error_response(code: str, message: str, status_code: int, request_id: str, details: Optional[Dict[str, Any]] = None) -> JSONResponse:
    """Format standardized JSON error response adhering to contract."""
    error_payload = {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
        }
    }
    if details:
        error_payload["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=error_payload)


async def floodlens_exception_handler(request: Request, exc: FloodLensAPIException) -> JSONResponse:
    request_id = get_request_id(request)
    return make_error_response(
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        request_id=request_id,
        details=exc.details,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    request_id = get_request_id(request)
    code_map = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        500: "INTERNAL_SERVER_ERROR",
        501: "NOT_IMPLEMENTED",
    }
    code = code_map.get(exc.status_code, "HTTP_ERROR")
    return make_error_response(
        code=code,
        message=str(exc.detail),
        status_code=exc.status_code,
        request_id=request_id,
    )


from fastapi.encoders import jsonable_encoder

async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = get_request_id(request)
    error_messages = []
    for err in exc.errors():
        loc = " -> ".join(str(l) for l in err.get("loc", []))
        msg = err.get("msg", "Validation error")
        error_messages.append(f"{loc}: {msg}")
    combined_message = "; ".join(error_messages) if error_messages else "Request validation failed"
    return make_error_response(
        code="VALIDATION_ERROR",
        message=combined_message,
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        request_id=request_id,
        details={"validation_errors": jsonable_encoder(exc.errors())},
    )
