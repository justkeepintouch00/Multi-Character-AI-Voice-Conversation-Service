from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import engine
from app.schemas.health import DatabaseHealthResponse, ServiceHealthResponse


router = APIRouter(tags=["health"])


def database_is_reachable() -> bool:
    """Return whether PostgreSQL can answer a minimal query.

    Database exception details are intentionally not returned to the client
    because connection strings and driver messages can contain sensitive data.
    """

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return False
    return True


@router.get(
    "/health",
    response_model=ServiceHealthResponse,
    summary="FastAPI 서버 상태 확인",
)
def get_service_health() -> ServiceHealthResponse:
    """Liveness check that does not depend on external services."""

    return ServiceHealthResponse()


@router.get(
    "/health/db",
    response_model=DatabaseHealthResponse,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": DatabaseHealthResponse,
            "description": "PostgreSQL에 연결할 수 없음",
        }
    },
    summary="PostgreSQL 연결 상태 확인",
)
def get_database_health(response: Response) -> DatabaseHealthResponse:
    """Readiness check for the PostgreSQL dependency."""

    if not database_is_reachable():
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return DatabaseHealthResponse(status="error", database="disconnected")

    return DatabaseHealthResponse(status="ok", database="connected")
