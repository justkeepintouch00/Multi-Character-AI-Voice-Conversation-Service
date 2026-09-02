from fastapi import APIRouter

from app.api.routes import (
    audio,
    characters,
    conversations,
    health,
    memory,
    observability,
    profile,
    scene_plans,
    scenarios,
    speech,
    transcriptions,
)


api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(characters.router)
api_router.include_router(conversations.router)
api_router.include_router(memory.router)
api_router.include_router(observability.router)
api_router.include_router(observability.prometheus_router)
api_router.include_router(profile.router)
api_router.include_router(scene_plans.router)
api_router.include_router(scenarios.router)
api_router.include_router(transcriptions.router)
api_router.include_router(audio.router)
api_router.include_router(speech.router)
