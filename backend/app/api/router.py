from fastapi import APIRouter

from app.api.routes import (
    audio,
    conversations,
    health,
    scene_plans,
    speech,
    transcriptions,
)


api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(conversations.router)
api_router.include_router(scene_plans.router)
api_router.include_router(transcriptions.router)
api_router.include_router(audio.router)
api_router.include_router(speech.router)
