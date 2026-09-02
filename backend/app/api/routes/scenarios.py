from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_scenario_service
from app.schemas.scenario import ScenarioDraftRead, ScenarioDraftWrite
from app.services.scenarios import ScenarioService


router = APIRouter(prefix="/api/v1/scenarios", tags=["scenarios"])


@router.get("", response_model=list[ScenarioDraftRead], summary="내 시나리오 목록 조회")
def list_scenario_drafts(
    service: Annotated[ScenarioService, Depends(get_scenario_service)],
) -> list[ScenarioDraftRead]:
    return service.list_drafts()
@router.get("/{scenario_id}", response_model=ScenarioDraftRead, summary="시나리오 초안 조회")
def get_scenario_draft(
    scenario_id: str,
    service: Annotated[ScenarioService, Depends(get_scenario_service)],
) -> ScenarioDraftRead:
    return service.get_draft(scenario_id)


@router.post(
    "",
    response_model=ScenarioDraftRead,
    status_code=status.HTTP_201_CREATED,
    summary="시나리오 초안 저장 또는 게시",
)
def create_scenario_draft(
    request: ScenarioDraftWrite,
    service: Annotated[ScenarioService, Depends(get_scenario_service)],
) -> ScenarioDraftRead:
    try:
        return service.save_draft(request)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error


@router.put(
    "/{scenario_id}",
    response_model=ScenarioDraftRead,
    summary="시나리오 초안 갱신 또는 게시",
)
def update_scenario_draft(
    scenario_id: str,
    request: ScenarioDraftWrite,
    service: Annotated[ScenarioService, Depends(get_scenario_service)],
) -> ScenarioDraftRead:
    try:
        return service.save_draft(request, scenario_id=scenario_id)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error

