from app.repositories.scenarios import SQLAlchemyScenarioRepository
from app.schemas.scenario import ScenarioDraftRead, ScenarioDraftWrite
from app.services.errors import ResourceNotFoundError


class ScenarioService:
    def __init__(self, repository: SQLAlchemyScenarioRepository) -> None:
        self.repository = repository

    def list_drafts(self) -> list[ScenarioDraftRead]:
        return self.repository.list_drafts()
    def get_draft(self, scenario_id: str) -> ScenarioDraftRead:
        scenario = self.repository.get_draft(scenario_id)
        if scenario is None:
            raise ResourceNotFoundError("시나리오를 찾을 수 없습니다.")
        return scenario

    def save_draft(
        self, request: ScenarioDraftWrite, *, scenario_id: str | None = None
    ) -> ScenarioDraftRead:
        scenario = self.repository.save_draft(request, scenario_id=scenario_id)
        if scenario is None:
            raise ResourceNotFoundError("시나리오를 찾을 수 없습니다.")
        return scenario

