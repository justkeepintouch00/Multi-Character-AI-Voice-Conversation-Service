from fastapi import FastAPI

from app.api.router import api_router


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
    application.include_router(api_router)
    return application


app = create_app()
