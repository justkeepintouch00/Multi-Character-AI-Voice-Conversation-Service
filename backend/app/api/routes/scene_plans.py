from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_scene_director_provider
from app.providers.base import SceneDirectorProvider
from app.schemas.scene_plan import ScenePlan, ScenePlanRequest


router = APIRouter(prefix="/api/v1/scene-plans", tags=["scene-director"])


@router.post(
    "",
    response_model=ScenePlan,
    status_code=status.HTTP_200_OK,
    summary="사용자 발화에 대한 캐릭터 발화 계획 생성",
)
async def create_scene_plan(
    request: ScenePlanRequest,
    provider: Annotated[SceneDirectorProvider, Depends(get_scene_director_provider)],
) -> ScenePlan:
    return await provider.create_scene_plan(request)
