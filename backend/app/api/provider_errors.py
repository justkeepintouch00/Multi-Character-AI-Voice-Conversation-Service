from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.providers.base import (
    ProviderConfigurationError,
    ProviderError,
    ProviderInputError,
    ProviderTimeoutError,
)


async def provider_error_handler(
    request: Request, exc: ProviderError
) -> JSONResponse:
    del request
    if isinstance(exc, ProviderInputError):
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        code = "INVALID_PROVIDER_INPUT"
    elif isinstance(exc, ProviderConfigurationError):
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        code = "PROVIDER_NOT_CONFIGURED"
    elif isinstance(exc, ProviderTimeoutError):
        status_code = status.HTTP_504_GATEWAY_TIMEOUT
        code = "UPSTREAM_TIMEOUT"
    else:
        status_code = status.HTTP_502_BAD_GATEWAY
        code = "UPSTREAM_ERROR"

    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": str(exc),
                "provider": exc.provider,
            }
        },
    )
