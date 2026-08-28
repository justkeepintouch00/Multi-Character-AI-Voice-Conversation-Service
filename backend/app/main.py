from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.provider_errors import provider_error_handler
from app.api.router import api_router
from app.api.service_errors import service_error_handler
from app.config import get_cors_origins
from app.observability import configure_logging
from app.observability.middleware import RequestObservabilityMiddleware
from app.providers.base import ProviderError
from app.services.errors import ServiceError


def create_app() -> FastAPI:
    configure_logging()
    application = FastAPI(
        title="Character Companion API",
        version="0.1.0",
        description="서브컬처 캐릭터 기반 멀티 AI 음성 동반자 서비스의 백엔드 API",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=get_cors_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    application.add_middleware(RequestObservabilityMiddleware)
    application.add_exception_handler(ProviderError, provider_error_handler)
    application.add_exception_handler(ServiceError, service_error_handler)
    application.include_router(api_router)

    upload_directory = Path(__file__).resolve().parents[1] / "uploads"
    upload_directory.mkdir(parents=True, exist_ok=True)
    application.mount("/uploads", StaticFiles(directory=upload_directory), name="uploads")
    return application


app = create_app()
