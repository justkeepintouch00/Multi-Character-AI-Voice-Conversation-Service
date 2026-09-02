import logging

from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.observability import METRICS, log_event
from app.providers.base import (
    ProviderConfigurationError,
    ProviderError,
    ProviderInputError,
    ProviderRequestError,
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
    elif isinstance(exc, ProviderRequestError) and exc.status_code == 429:
        status_code = status.HTTP_429_TOO_MANY_REQUESTS
        code = exc.error_code or "rate_limit_exceeded"
    else:
        status_code = status.HTTP_502_BAD_GATEWAY
        code = "UPSTREAM_ERROR"

    headers = None
    if isinstance(exc, ProviderRequestError) and exc.retry_after:
        headers = {"Retry-After": exc.retry_after}
    upstream_status = (
        exc.status_code if isinstance(exc, ProviderRequestError) else None
    )
    error_kind = (
        "timeout" if isinstance(exc, ProviderTimeoutError)
        else str(upstream_status or code)
    )
    METRICS.increment(
        "provider_errors_total",
        provider=exc.provider,
        error=error_kind,
        response_status=status_code,
        upstream_status=upstream_status or "none",
    )
    log_event(
        "provider_error",
        level=logging.ERROR,
        provider=exc.provider,
        error_code=code,
        response_status=status_code,
        upstream_status=upstream_status,
    )

    return JSONResponse(
        status_code=status_code,
        headers=headers,
        content={
            "error": {
                "code": code,
                "message": str(exc),
                "provider": exc.provider,
                "upstream_status": upstream_status,
            }
        },
    )
