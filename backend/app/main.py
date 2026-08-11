from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.provider_errors import provider_error_handler
from app.api.router import api_router
from app.api.service_errors import service_error_handler
from app.config import get_cors_origins
from app.providers.base import ProviderError
from app.services.errors import ServiceError


def create_app() -> FastAPI:
    application = FastAPI(
        title="Character Companion API",
        version="0.1.0",
        description=(
            "서브컬처 캐릭터 기반 멀티 AI 음성 동반자 서비스의 백엔드 API"
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=get_cors_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )
    application.add_exception_handler(ProviderError, provider_error_handler)
    application.add_exception_handler(ServiceError, service_error_handler)
    application.include_router(api_router)
    return application


app = create_app()
