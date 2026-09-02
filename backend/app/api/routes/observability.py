from fastapi import APIRouter
from fastapi.responses import Response

from app.observability.metrics import METRICS
from app.observability.prometheus import prometheus_exposition


router = APIRouter(prefix="/api/v1/observability", tags=["observability"])


@router.get(
    "/metrics",
    summary="단일 백엔드 프로세스의 관측성 메트릭 조회",
)
def get_metrics() -> dict:
    return METRICS.snapshot()


prometheus_router = APIRouter(tags=["observability"])


@prometheus_router.get(
    "/metrics",
    summary="Prometheus 호환 관측성 메트릭 조회",
    include_in_schema=True,
)
def get_prometheus_metrics() -> Response:
    return Response(
        content=prometheus_exposition(METRICS.snapshot()),
        media_type="text/plain; version=0.0.4",
    )
