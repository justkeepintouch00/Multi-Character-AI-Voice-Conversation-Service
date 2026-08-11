from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.services.errors import (
    InvalidResourceInputError,
    ResourceConflictError,
    ResourceNotFoundError,
    ServiceError,
)


async def service_error_handler(request: Request, exc: ServiceError) -> JSONResponse:
    del request
    if isinstance(exc, ResourceNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
        code = "RESOURCE_NOT_FOUND"
    elif isinstance(exc, ResourceConflictError):
        status_code = status.HTTP_409_CONFLICT
        code = "RESOURCE_CONFLICT"
    elif isinstance(exc, InvalidResourceInputError):
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        code = "INVALID_RESOURCE_INPUT"
    else:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        code = "SERVICE_ERROR"
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": str(exc)}},
    )
